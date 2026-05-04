"""Build a formatted DOCX from plain-text resume content.

Matches the original Alex Costa Souza resume format:
  - Font: Arial throughout
  - Margins: 0.5" on all sides
  - Name: 18pt bold
  - Contact line: 10pt
  - Section headers: 12pt bold
  - Skill lines (Label: content): label bold 10pt, value regular 10pt
  - Job headers: bold title+company 11pt + regular date+location 10pt
  - Bullet points: List Bullet style, 10pt
  - Education degree lines: bold 10pt, institution lines: regular 10pt
  - All other lines: regular 10pt
"""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

_SECTION_HEADERS = {
    "Professional Summary",
    "Skills",
    "Work Experience",
    "Personal Projects",
    "Education",
    "Certifications",
    "Languages",
    "Awards",
}

_EXPERIENCE_SECTIONS = {"Work Experience", "Personal Projects"}

# Matches a month+year or standalone year that signals a job date range
_DATE_RE = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b"
    r"|\bPresent\b"
)

_DEGREE_PREFIXES = (
    "Associate",
    "Bachelor",
    "Master",
    "Doctor",
    "PhD",
    "MBA",
    "B.S",
    "M.S",
    "B.A",
    "M.A",
)


def _set_font(run: Any, bold: bool, size_pt: float) -> None:
    run.bold = bold
    run.font.name = "Arial"
    run.font.size = Pt(size_pt)
    run._element.rPr.rFonts.set(qn("w:asciiTheme"), "")
    run._element.rPr.rFonts.set(qn("w:hAnsiTheme"), "")


def _add_run(para: Any, text: str, bold: bool, size_pt: float) -> None:
    run = para.add_run(text)
    run.bold = bold
    run.font.name = "Arial"
    run.font.size = Pt(size_pt)


def _split_job_header(line: str) -> tuple[str, str]:
    """Split 'Title — Company Oct 2025 to Present | Location' into (bold, regular)."""
    m = _DATE_RE.search(line)
    if m:
        return line[: m.start()].rstrip(), " " + line[m.start() :]
    return line, ""


def build_resume_docx(text: str) -> bytes:
    doc = Document()

    # Remove the default empty paragraph python-docx adds
    for p in doc.paragraphs:
        p._element.getparent().remove(p._element)

    # Set page margins
    for sec in doc.sections:
        sec.top_margin = Inches(0.5)
        sec.bottom_margin = Inches(0.5)
        sec.left_margin = Inches(0.5)
        sec.right_margin = Inches(0.5)

    lines = [ln.strip() for ln in text.strip().splitlines()]
    current_section: str | None = None

    for idx, line in enumerate(lines):
        if not line:
            continue

        # ── Name ───────────────────────────────────────────────────────────
        if idx == 0:
            p = doc.add_paragraph()
            _add_run(p, line, bold=True, size_pt=18)
            continue

        # ── Contact line ───────────────────────────────────────────────────
        if idx == 1:
            p = doc.add_paragraph()
            _add_run(p, line, bold=False, size_pt=10)
            continue

        # ── Section header ─────────────────────────────────────────────────
        if line in _SECTION_HEADERS:
            current_section = line
            p = doc.add_paragraph()
            _add_run(p, line, bold=True, size_pt=12)
            continue

        # ── Skills section ─────────────────────────────────────────────────
        if current_section == "Skills":
            p = doc.add_paragraph()
            if ": " in line:
                label, _, rest = line.partition(": ")
                _add_run(p, label + ": ", bold=True, size_pt=10)
                _add_run(p, rest, bold=False, size_pt=10)
            else:
                _add_run(p, line, bold=True, size_pt=10)
            continue

        # ── Work Experience / Personal Projects ────────────────────────────
        if current_section in _EXPERIENCE_SECTIONS:
            if _DATE_RE.search(line):
                # Job header: split at date
                bold_part, regular_part = _split_job_header(line)
                p = doc.add_paragraph()
                if bold_part:
                    _add_run(p, bold_part, bold=True, size_pt=11)
                if regular_part:
                    _add_run(p, regular_part, bold=False, size_pt=10)
            else:
                # Bullet
                p = doc.add_paragraph(style="List Bullet")
                _add_run(p, line, bold=False, size_pt=10)
            continue

        # ── Education ──────────────────────────────────────────────────────
        if current_section == "Education":
            is_degree = line.startswith(_DEGREE_PREFIXES)
            p = doc.add_paragraph()
            _add_run(p, line, bold=is_degree, size_pt=10)
            continue

        # ── Certifications / everything else ───────────────────────────────
        p = doc.add_paragraph()
        _add_run(p, line, bold=False, size_pt=10)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
