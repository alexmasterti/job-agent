"""Resume PDF/DOCX → structured Profile parser using pypdf + LLM extraction."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from pypdf import PdfReader
from docx import Document

from job_agent.domain.models.profile import Profile
from job_agent.infrastructure.llm.anthropic_client import AnthropicClient

log = structlog.get_logger()

_EXTRACTION_SYSTEM = """
You are a resume parser. Extract structured data from the resume text below.
Return ONLY valid JSON — no markdown fences, no commentary.

JSON schema (all fields optional, use empty lists/strings for missing data):
{
  "full_name": "string",
  "headline": "string",
  "summary": "string",
  "skills": ["string"],
  "experience": [
    {
      "company": "string",
      "title": "string",
      "start": "YYYY-MM or YYYY",
      "end": "YYYY-MM or YYYY or present",
      "location": "string",
      "bullets": ["string"]
    }
  ],
  "education": [
    {
      "institution": "string",
      "degree": "string",
      "field": "string",
      "year": "string"
    }
  ],
  "certifications": ["string"],
  "languages": [
    {"language": "string", "proficiency": "string"}
  ]
}
"""


def extract_text_from_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def extract_text_from_docx(path: Path) -> str:
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip()).strip()


async def parse_resume(
    file_path: Path,
    user_id: uuid.UUID,
    llm: AnthropicClient,
) -> Profile:
    """Parse a PDF or DOCX resume into a structured Profile domain object."""
    if not file_path.exists():
        raise FileNotFoundError(f"Resume not found: {file_path}")

    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        resume_text = extract_text_from_pdf(file_path)
    elif suffix in (".docx", ".doc"):
        resume_text = extract_text_from_docx(file_path)
    else:
        raise ValueError(f"Unsupported format: {suffix}. Supported: .pdf, .docx")

    log.info("parser.extract", user_id=str(user_id), chars=len(resume_text))

    structured = await _llm_extract(resume_text, user_id, llm)

    now = datetime.now(timezone.utc)
    return Profile(
        id=uuid.uuid4(),
        user_id=user_id,
        created_at=now,
        updated_at=now,
        resume_text=resume_text,
        **structured,
    )


async def _llm_extract(text: str, user_id: uuid.UUID, llm: AnthropicClient) -> dict[str, Any]:
    """Call Haiku to convert raw resume text to structured JSON."""
    response = await llm.complete(
        user_id=user_id,
        purpose="resume_parse",
        system=_EXTRACTION_SYSTEM,
        prompt=f"<resume>\n{text[:12000]}\n</resume>",
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        temperature=0.1,
    )

    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0].strip()

    try:
        data: dict[str, Any] = json.loads(cleaned)
        return data
    except json.JSONDecodeError:
        pass

    # Try to extract just the outermost JSON object if full parse fails
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group())
            return data
        except json.JSONDecodeError as exc:
            log.error("parser.json_error", error=str(exc), raw=response[:200])

    log.error("parser.json_error", error="no valid JSON found", raw=response[:200])
    return {}
