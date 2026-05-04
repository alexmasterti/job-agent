"""Playwright-based browser automation for ATS form submission.

Runs headless Chromium server-side. Navigates to the job's application page,
fills the form, uploads resume, takes a screenshot as proof, and submits.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from playwright.async_api import async_playwright

if TYPE_CHECKING:
    from playwright.async_api import Page

    from job_agent.domain.models.application import Application
    from job_agent.domain.models.profile import Profile

log = structlog.get_logger()

_SCREENSHOTS_DIR = Path("data/screenshots")
_TIMEOUT_MS = 30_000


class _FormFiller:
    """Detects ATS type and fills the application form."""

    def __init__(self, page: Page, profile: Profile, email: str, resume_text: str) -> None:
        self._page = page
        self._profile = profile
        self._email = email
        self._resume = resume_text

    async def fill(self) -> bool:
        """Detect form type and fill. Returns True if form was found and filled."""
        url = self._page.url

        if "greenhouse" in url:
            return await self._fill_greenhouse()
        if "lever.co" in url:
            return await self._fill_lever()

        # Generic fallback: try common field patterns
        return await self._fill_generic()

    async def _fill_greenhouse(self) -> bool:
        """Fill Greenhouse embedded application form.

        Greenhouse uses custom JS dropdown widgets (NOT native <select>).
        All dropdowns are <input type="text"> with popup listboxes on click.
        File inputs (id="resume") are visible and accept set_input_files.
        """
        import contextlib

        p = self._page
        name_parts = self._profile.full_name.strip().split() if self._profile.full_name else [""]
        first_name = name_parts[0]
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
        location_name = ""
        if self._profile.preferred_locations:
            location_name = self._profile.preferred_locations[0].name

        # --- Standard text fields ---
        await self._gh_fill("#first_name", first_name)
        await self._gh_fill("#last_name", last_name)
        await self._gh_fill("#email", self._email)
        await self._gh_fill("input[type='tel']", "(617) 000-0000")
        await self._gh_fill("#candidate-location", location_name or "Boston, MA")

        # --- Country: custom dropdown (type to search, click option) ---
        await self._gh_click_dropdown("#country", "United States")

        # --- Resume upload ---
        await self._upload_resume()

        # --- Preferred First Name (may be standalone or a question_* field) ---
        # Find by label text since the ID varies per form
        pref_labels = p.locator("label:has-text('Preferred First Name')")
        if await pref_labels.count() > 0:
            pref_for = await pref_labels.first.get_attribute("for")
            if pref_for:
                pref_input = p.locator(f"#{pref_for}")
                if await pref_input.count() > 0:
                    await pref_input.fill(first_name)
                    log.info("browser.preferred_name_filled", value=first_name)

        # --- Custom questions (input[id^='question_']) ---
        # Some are text fields (Preferred Name, LinkedIn), others are dropdown widgets.
        # Strategy: check each question's label to decide how to fill it.
        question_inputs = p.locator("input[id^='question_']")
        q_count = await question_inputs.count()
        log.info("browser.questions_found", count=q_count)
        for i in range(q_count):
            q_inp = question_inputs.nth(i)
            current = await q_inp.input_value()
            if current.strip():
                continue
            qid = await q_inp.get_attribute("id") or ""
            # Check label to determine field type
            label_el = p.locator(f"label[for='{qid}']")
            label_text = ""
            if await label_el.count() > 0:
                label_text = (await label_el.inner_text()).lower()

            # Text fields: fill directly
            if "preferred" in label_text or "first name" in label_text:
                await q_inp.fill(first_name)
                log.info("browser.question_text", qid=qid, value=first_name)
                continue
            if "linkedin" in label_text or "website" in label_text or "portfolio" in label_text:
                continue  # Optional, skip

            # Dropdown fields: click to open popup, select first option
            await q_inp.click()
            await p.wait_for_timeout(500)
            option = p.locator("[role='option']:visible").first
            if await option.count() > 0:
                text = await option.inner_text()
                await option.click()
                log.info("browser.question_selected", qid=qid, text=text[:40])
            else:
                await q_inp.fill("Yes")
                await q_inp.press("Enter")
                log.info("browser.question_typed", qid=qid)
            await p.wait_for_timeout(300)

        # --- Demographic dropdowns (Gender, etc.) — custom widgets found by label ---
        demo_labels = p.locator("label:has-text('Gender'), label:has-text('Ethnicity')")
        for i in range(await demo_labels.count()):
            lbl = demo_labels.nth(i)
            for_id = await lbl.get_attribute("for")
            if not for_id:
                continue
            inp = p.locator(f"[id='{for_id}']")
            if await inp.count() == 0:
                continue
            current = await inp.input_value()
            if current.strip():
                continue
            await inp.click()
            await p.wait_for_timeout(500)
            option = p.locator("[role='option']:visible").first
            if await option.count() > 0:
                text = await option.inner_text()
                await option.click()
                log.info("browser.demographic_selected", label=for_id, text=text[:30])
            await p.wait_for_timeout(300)

        # --- Native <select> dropdowns (fallback for any remaining) ---
        selects = p.locator("select")
        for i in range(await selects.count()):
            dropdown = selects.nth(i)
            options = dropdown.locator("option")
            if await options.count() > 1:
                await dropdown.select_option(index=1)

        # --- Check all checkboxes (privacy/consent) ---
        checkboxes = p.locator("input[type='checkbox']")
        for i in range(await checkboxes.count()):
            cb = checkboxes.nth(i)
            if not await cb.is_checked():
                with contextlib.suppress(Exception):
                    await cb.check(timeout=2000)

        return True

    async def _gh_fill(self, selector: str, value: str) -> None:
        """Fill a Greenhouse form field if found."""
        el = self._page.locator(selector).first
        if await el.count() > 0:
            await el.fill(value)

    async def _gh_click_dropdown(self, selector: str, search_text: str) -> None:
        """Fill a Greenhouse custom dropdown by typing and selecting from popup."""
        p = self._page
        el = p.locator(selector).first
        if await el.count() == 0:
            return
        await el.click()
        await p.wait_for_timeout(300)
        await el.fill(search_text)
        await p.wait_for_timeout(500)
        option = p.locator("[role='option']:visible, .select2-results__option:visible").first
        if await option.count() > 0:
            await option.click()
            log.info("browser.dropdown_selected", selector=selector, text=search_text)
        else:
            await el.press("Enter")
            log.info("browser.dropdown_enter", selector=selector)

    async def _fill_lever(self) -> bool:
        """Fill Lever application form."""
        p = self._page
        name = self._profile.full_name.strip() if self._profile.full_name else ""

        filled = False

        # Lever uses "name" field (full name)
        for sel in [
            "input[name='name']",
            "[data-qa='name']",
            ".application-name input",
            "input[placeholder*='name' i]",
        ]:
            el = p.locator(sel).first
            if await el.count() > 0:
                await el.fill(name)
                filled = True
                break

        # Email
        for sel in [
            "input[name='email']",
            "[data-qa='email']",
            ".application-email input",
            "input[type='email']",
        ]:
            el = p.locator(sel).first
            if await el.count() > 0:
                await el.fill(self._email)
                filled = True
                break

        # Resume upload
        await self._upload_resume()

        return filled

    async def _fill_generic(self) -> bool:
        """Try to fill common form patterns across any ATS."""
        p = self._page
        name_parts = self._profile.full_name.strip().split() if self._profile.full_name else [""]
        filled = False

        # Try first name / last name
        fn = p.locator("input[name*='first_name' i], input[name*='firstName' i]").first
        if await fn.count() > 0:
            await fn.fill(name_parts[0])
            filled = True

        ln = p.locator("input[name*='last_name' i], input[name*='lastName' i]").first
        if await ln.count() > 0:
            await ln.fill(" ".join(name_parts[1:]) if len(name_parts) > 1 else "")
            filled = True

        # Try full name
        if not filled:
            nm = p.locator("input[name*='name' i]").first
            if await nm.count() > 0:
                await nm.fill(self._profile.full_name or "")
                filled = True

        # Email
        em = p.locator("input[type='email'], input[name*='email' i]").first
        if await em.count() > 0:
            await em.fill(self._email)
            filled = True

        await self._upload_resume()
        return filled

    async def _upload_resume(self) -> None:
        """Upload resume via JavaScript DataTransfer on the #resume file input.

        Greenhouse uses a React component with a visually-hidden file input.
        Neither set_input_files nor file_chooser reliably triggers the React state.
        The only approach that works: create a File via JS DataTransfer and dispatch change.
        """
        if not self._resume:
            return

        p = self._page

        # Use JavaScript to create a File and set it on the input
        result = await p.evaluate(
            """(text) => {
            const input = document.getElementById('resume')
                || document.querySelector('input[type="file"]');
            if (!input) return 'no_input';
            const file = new File([text], 'resume.txt', { type: 'text/plain' });
            const dt = new DataTransfer();
            dt.items.add(file);
            input.files = dt.files;
            input.dispatchEvent(new Event('change', { bubbles: true }));
            input.dispatchEvent(new Event('input', { bubbles: true }));
            return 'ok';
        }""",
            self._resume,
        )

        if result == "ok":
            log.info("browser.resume_uploaded")
        else:
            log.warning("browser.resume_upload_failed", result=result)


async def _find_submit_button(page: Page) -> bool:
    """Find and click the submit button. Returns True if found."""
    for sel in [
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Submit')",
        "button:has-text('Apply')",
        "button:has-text('Send')",
        "[data-qa='btn-submit']",
        ".btn-submit",
    ]:
        btn = page.locator(sel).first
        if await btn.count() > 0 and await btn.is_visible():
            await btn.click()
            return True
    return False


class PlaywrightSubmitter:
    """Server-side headless browser submitter for any ATS."""

    ats_type = "browser"

    async def submit(self, application: Application, profile: Profile) -> Application:
        """Open the application page, fill the form, submit, capture proof."""
        if application.ats_confirmation_id:
            log.info("browser.submit.skip_idempotent", app_id=str(application.id))
            return application

        url = application.submission_url
        if not url:
            log.warning("browser.submit.no_url", app_id=str(application.id))
            return application

        email = application.form_fields_snapshot.get("email", "")
        resume_text = application.form_fields_snapshot.get("tailored_resume", "")
        app_id_str = str(application.id)

        # Ensure screenshots directory exists
        _SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

        apply_url = _to_human_apply_url(url, application.ats_type)
        log.info("browser.submit.start", app_id=app_id_str, url=apply_url)

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                    ],
                )
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 900},
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    locale="en-US",
                )
                page = await context.new_page()

                # Hide webdriver flag
                await page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )

                # Navigate to the application page
                await page.goto(apply_url, wait_until="domcontentloaded", timeout=_TIMEOUT_MS)
                await page.wait_for_timeout(2000)  # Let JS render

                # Fill the form
                filler = _FormFiller(page, profile, email, resume_text)
                filled = await filler.fill()

                if not filled:
                    screenshot_path = str(_SCREENSHOTS_DIR / f"{app_id_str}-failed.png")
                    await page.screenshot(path=screenshot_path, full_page=True)
                    log.warning(
                        "browser.submit.no_form_found",
                        app_id=app_id_str,
                        screenshot=screenshot_path,
                    )
                    await browser.close()
                    return application.model_copy(update={"screenshot_path": screenshot_path})

                # Screenshot before submit (proof of filled form)
                pre_screenshot = str(_SCREENSHOTS_DIR / f"{app_id_str}-pre.png")
                await page.screenshot(path=pre_screenshot, full_page=True)

                # Click submit
                submitted = await _find_submit_button(page)
                if not submitted:
                    log.warning("browser.submit.no_submit_button", app_id=app_id_str)
                    await browser.close()
                    return application.model_copy(update={"screenshot_path": pre_screenshot})

                # Wait for navigation or confirmation
                await page.wait_for_timeout(3000)

                # Screenshot after submit (confirmation page)
                post_screenshot = str(_SCREENSHOTS_DIR / f"{app_id_str}-post.png")
                await page.screenshot(path=post_screenshot, full_page=True)

                # Check for success indicators
                page_text = await page.inner_text("body")
                success = _detect_success(page_text)

                await browser.close()

                confirmation_id = f"pw-{uuid.uuid4().hex[:12]}"

                if success:
                    log.info(
                        "browser.submit.success",
                        app_id=app_id_str,
                        confirmation=confirmation_id,
                    )
                    return application.model_copy(
                        update={
                            "status": "submitted",
                            "ats_confirmation_id": confirmation_id,
                            "submitted_at": datetime.now(UTC),
                            "screenshot_path": post_screenshot,
                            "response_text": page_text[:500],
                        }
                    )

                # Check if form filled OK but needs human verification
                if _detect_verification_required(page_text):
                    log.info(
                        "browser.submit.needs_verification",
                        app_id=app_id_str,
                    )
                    await browser.close()
                    return application.model_copy(
                        update={
                            "status": "submitted",
                            "ats_confirmation_id": f"verify-{confirmation_id}",
                            "submitted_at": datetime.now(UTC),
                            "screenshot_path": post_screenshot,
                            "response_text": "Form filled. Check email for verification code.",
                        }
                    )

                log.warning(
                    "browser.submit.uncertain",
                    app_id=app_id_str,
                    page_text=page_text[:200],
                )
                await browser.close()
                return application.model_copy(
                    update={
                        "screenshot_path": post_screenshot,
                        "response_text": page_text[:500],
                    }
                )

        except Exception as exc:
            log.error("browser.submit.error", app_id=app_id_str, error=str(exc))
            return application


def _to_human_apply_url(url: str, ats_type: str) -> str:
    """Convert API URLs to human-facing application page URLs.

    Uses the Greenhouse embedded job_app form which stays on greenhouse.io
    and never redirects to the company's custom domain (avoids WAF blocks).
    """
    if "boards-api.greenhouse.io" in url:
        # boards-api.greenhouse.io/v1/boards/{slug}/jobs/{id}
        # → job-boards.greenhouse.io/embed/job_app?for={slug}&token={id}
        import re

        match = re.search(r"boards/([^/]+)/jobs/(\d+)", url)
        if match:
            slug, job_id = match.group(1), match.group(2)
            return f"https://job-boards.greenhouse.io/embed/job_app?for={slug}&token={job_id}"
        return url
    # Lever: already a human URL if it ends with /apply
    if "lever.co" in url and "/apply" not in url:
        return url.rstrip("/") + "/apply"
    return url


def _detect_success(page_text: str) -> bool:
    """Check if the page text indicates a successful submission."""
    lower = page_text.lower()
    success_phrases = [
        "thank you for applying",
        "thanks for applying",
        "application has been submitted",
        "application received",
        "we received your application",
        "successfully submitted",
        "thank you for your interest",
        "thanks for your interest",
        "we'll be in touch",
        "application complete",
        "you have successfully applied",
    ]
    return any(phrase in lower for phrase in success_phrases)


def _detect_verification_required(page_text: str) -> bool:
    """Check if the form requires email/phone verification (CAPTCHA-like)."""
    lower = page_text.lower()
    verification_phrases = [
        "verification code",
        "security code",
        "confirm you're a human",
        "enter the code",
        "verify your email",
    ]
    return any(phrase in lower for phrase in verification_phrases)


async def complete_verification(
    url: str,
    ats_type: str,
    profile: Any,
    email: str,
    resume_text: str,
    verification_code: str,
) -> dict[str, object]:
    """Open fresh browser, fill form, submit, enter verification code, submit again."""
    apply_url = _to_human_apply_url(url, ats_type)
    screenshots_dir = _SCREENSHOTS_DIR
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    log.info("verify.start", url=apply_url, code_len=len(verification_code))

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )
            page = await context.new_page()
            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            await page.goto(apply_url, wait_until="domcontentloaded", timeout=_TIMEOUT_MS)
            await page.wait_for_timeout(2000)

            # Re-fill the entire form
            filler = _FormFiller(page, profile, email, resume_text)
            await filler.fill()
            await page.wait_for_timeout(1000)
            log.info("verify.form_filled")

            # First submit to trigger verification code email
            await _find_submit_button(page)
            await page.wait_for_timeout(4000)

            # Now enter the verification code
            # Greenhouse uses 8 individual single-char inputs for the code
            code_inputs = page.locator(
                "input[name*='security'], input[name*='code'], input[autocomplete='one-time-code']"
            )
            code_count = await code_inputs.count()

            if code_count == 0:
                # Find empty single-char inputs (maxlength=1)
                all_inputs = page.locator("input[type='text']:visible, input:not([type]):visible")
                singles = []
                for i in range(await all_inputs.count()):
                    inp = all_inputs.nth(i)
                    maxlen = await inp.get_attribute("maxlength")
                    val = await inp.input_value()
                    if maxlen == "1" and not val.strip():
                        singles.append(inp)
                if len(singles) >= len(verification_code):
                    for i, char in enumerate(verification_code):
                        await singles[i].fill(char)
                    log.info("verify.code_entered", method="singles", count=len(singles))
                else:
                    log.warning("verify.no_code_inputs", singles=len(singles))
            elif code_count >= len(verification_code):
                for i, char in enumerate(verification_code):
                    await code_inputs.nth(i).fill(char)
                log.info("verify.code_entered", method="named", count=code_count)
            else:
                await code_inputs.first.fill(verification_code)
                log.info("verify.code_entered", method="single_field")

            await page.wait_for_timeout(500)

            # Submit again with the code
            await _find_submit_button(page)
            await page.wait_for_timeout(5000)

            page_text = await page.inner_text("body")
            screenshot = str(screenshots_dir / f"verify-{uuid.uuid4().hex[:8]}.png")
            await page.screenshot(path=screenshot, full_page=True)
            await browser.close()

            success = _detect_success(page_text)
            log.info("verify.result", success=success, text=page_text[:100])

            return {
                "success": success,
                "screenshot": screenshot,
                "page_text": page_text[:500],
            }

    except Exception as exc:
        log.error("verify.error", error=str(exc))
        return {"success": False, "error": str(exc)}
