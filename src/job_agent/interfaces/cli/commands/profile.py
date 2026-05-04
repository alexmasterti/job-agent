"""profile sub-commands: load, show, seed."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from job_agent.composition_root import build_container
from job_agent.config import Settings
from job_agent.domain.models.user import User, UserTier
from job_agent.logging_config import configure_logging

if TYPE_CHECKING:
    from pathlib import Path

app = typer.Typer(help="Resume profile commands.")
console = Console()


def _run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


@app.command("load")
def load(
    resume_path: Annotated[Path, typer.Argument(help="Path to resume PDF")],
    user_email: str = typer.Option(..., "--user-email", "-u", help="Google email for the user"),
) -> None:
    """Parse a resume PDF and save the structured profile.

    Auto-creates the user row if the email is in ALLOWED_GOOGLE_EMAILS.
    """
    settings = Settings()  # type: ignore[call-arg]
    configure_logging(settings.app_env)

    if user_email.lower() not in settings.allowed_emails:
        console.print(f"[red]Email '{user_email}' is not in ALLOWED_GOOGLE_EMAILS.[/red]")
        raise typer.Exit(1)

    container = build_container(settings)

    async def _run_async() -> None:
        # Auto-create user row on first CLI run
        existing = await container.user_repo.get_by_email(user_email.lower())
        if not existing:
            user = User(
                id=uuid.uuid4(),
                email=user_email.lower(),
                google_sub=f"cli:{user_email.lower()}",
                tier=UserTier.pro,
                is_active=True,
                created_at=datetime.now(UTC),
            )
            existing = await container.user_repo.upsert(user)
            console.print(f"[green]Created user row for {user_email}[/green]")

        with console.status(f"Parsing {resume_path.name}..."):
            profile = await container.load_profile.execute(existing.id, resume_path)

        console.print(
            Panel(
                Syntax(
                    json.dumps(profile.model_dump(mode="json", exclude={"resume_text"}), indent=2),
                    "json",
                    theme="monokai",
                    word_wrap=True,
                ),
                title="[bold green]Profile Parsed[/bold green]",
                border_style="green",
            )
        )
        console.print(f"\n[green]Profile saved (id={profile.id})[/green]")

    _run(_run_async())


@app.command("show")
def show(
    user_email: str = typer.Option(..., "--user-email", "-u"),
) -> None:
    """Print the stored profile for a user."""
    settings = Settings()  # type: ignore[call-arg]
    container = build_container(settings)

    async def _run_async() -> None:
        user = await container.user_repo.get_by_email(user_email.lower())
        if not user:
            console.print(f"[red]No user found for {user_email}[/red]")
            raise typer.Exit(1)
        profile = await container.profile_repo.get_by_user(user.id)
        if not profile:
            console.print("[yellow]No profile loaded yet. Run: job-agent profile load[/yellow]")
            return
        console.print(
            Panel(
                Syntax(
                    json.dumps(profile.model_dump(mode="json", exclude={"resume_text"}), indent=2),
                    "json",
                    theme="monokai",
                    word_wrap=True,
                ),
                title=f"[bold]Profile — {profile.full_name or user_email}[/bold]",
            )
        )

    _run(_run_async())
