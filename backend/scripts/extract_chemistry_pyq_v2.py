#!/usr/bin/env python3
"""
Chemistry PYQ extraction using GPT-4o VISION (no OCR).

Sends PDF pages as images directly to GPT-4o which reads both English and
Tamil text natively — solving the garbled-Tamil problem from pytesseract.

Run from repository root:
  cd backend && python -u scripts/extract_chemistry_pyq_v2.py

Requires: Postgres (DATABASE_URL / .env), OPENAI_API_KEY, PDF on disk.
"""
from __future__ import annotations

import base64
import io
import os
import re
import sys

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)
os.chdir(BACKEND_ROOT)

from pathlib import Path

import fitz  # PyMuPDF — only for image rendering, NOT for OCR
from openai import OpenAI
from pydantic import BaseModel, Field

from app.config import settings
from app.database import SessionLocal
from app.models import PyqDocument, PyqIngestStatus, PyqQuestion, PyqSubject
from app.pyq_pipeline import (
    _align_mcq_options,
    _answer_key_for_db,
    _merge_bilingual_text,
    _options_display_lines,
    sync_pyq_catalog_from_files,
)

CHEMISTRY_PDF = Path("data/previous_year/chemistry__pyq__2020_2025.pdf")
SUBJECT_SLUG = "chemistry"
PAGES_PER_BATCH = 2   # pages per vision API call (2 keeps token usage manageable)
MAX_QUESTIONS = 500
RENDER_SCALE = 2.0    # PDF render scale — 2× gives ~1200×1700 px per page

_YEAR_RE = re.compile(r"20(\d{2})")


# ─── Page → exam/year map from pypdf watermarks ───────────────────────────────

def _build_page_exam_map(pdf_path: Path) -> dict[int, tuple[str, int]]:
    """
    Returns {page_index: (exam_label, year)} using pypdf to read the text-layer
    watermarks that are invisible to image OCR.
    """
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    mapping: dict[int, tuple[str, int]] = {}
    for i, page in enumerate(reader.pages):
        raw = (page.extract_text() or "").strip()
        if not raw:
            continue
        lines = [
            ln.strip()
            for ln in raw.splitlines()
            if ln.strip()
            and not ln.strip().isdigit()
            and "SCIENCE" not in ln.upper()
            and "CHEMISTRY" not in ln.upper()
        ]
        if not lines:
            continue
        exam_label = " | ".join(lines[:3])
        year_match = _YEAR_RE.search(raw)
        if year_match:
            year = int("20" + year_match.group(1))
            mapping[i] = (exam_label, year)
    return mapping


# ─── Pydantic schema for GPT-4o structured output ────────────────────────────

class ExtractedQuestion(BaseModel):
    question_en: str = Field(default="", description="Full English question stem (no options)")
    question_ta: str = Field(default="", description="Full Tamil question stem in Tamil Unicode (no options)")
    options_en: list[str] = Field(
        default_factory=list,
        description="Exactly 4 English option texts [A, B, C, D] without letter prefix",
    )
    options_ta: list[str] = Field(
        default_factory=list,
        description="Exactly 4 Tamil option texts [A, B, C, D] in Tamil Unicode, without letter prefix",
    )
    correct_answer: str = Field(
        default="",
        description="'A. <option text>' … 'D. <option text>' or 'E. Answer not known'",
    )
    explanation: str = Field(default="", description="Rationale/solution when present")
    exam: str | None = Field(default=None, description="Exam name from context e.g. 'G1 EXAM 2022'")
    year: int | None = Field(default=None, description="4-digit exam year integer")
    topic: str | None = Field(default=None, description="Chemistry topic e.g. 'Periodic Table'")


class ExtractedBatch(BaseModel):
    questions: list[ExtractedQuestion]


# ─── System prompt ────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are reading pages from a TNPSC (Tamil Nadu Public Service Commission) previous-year
chemistry question paper. The paper is bilingual: every MCQ appears once in English then
once in Tamil (or vice versa).

YOUR TASK
---------
For every distinct MCQ question visible in the page images:

1. question_en  — Copy the English question stem exactly (no options, no numbering).
2. question_ta  — Copy the Tamil question stem exactly in Tamil Unicode script.
                  The Tamil text uses standard Tamil Unicode. Output it faithfully,
                  do NOT transliterate or romanise it.
3. options_en   — Array of exactly 4 strings: [A_text, B_text, C_text, D_text].
                  Strip the leading "A." / "(A)" / "(a)" prefix; keep only the text.
                  If a particular option is not present leave it as "".
4. options_ta   — Same structure as options_en but for the Tamil options, in Tamil Unicode.
5. correct_answer — The correct option. In the original PDF the correct answer is
                  visually highlighted or circled. Look carefully: the highlighted option
                  has a darker/bolder background or a circle around its letter.
                  Format: "B. <English option text>"  (use English text even if Tamil
                  version is highlighted, so long as you can identify the letter).
                  If the printed answer is "(E) Answer not known" write "E. Answer not known".
                  If you cannot determine the answer, write "".
6. exam         — Use the exam context provided (page header / watermark info).
7. year         — Integer year from the exam context.
8. topic        — Short chemistry topic label (e.g. "Acids and Bases", "Periodic Table").
9. explanation  — Rationale if explicitly printed on the page; otherwise "".

RULES
-----
• Output Tamil text in Tamil Unicode — நேரடியாக Tamil script.
• Do NOT romanise Tamil (no "Epsom", "Sapren", etc.).
• Skip page numbers, watermarks, section headers, index rows.
• Do NOT fabricate text. Extract only what is printed.
• Return ALL MCQ questions visible in the page images.
"""


# ─── Vision helpers ───────────────────────────────────────────────────────────

def _render_pages_b64(pdf_path: Path, start: int, end: int) -> list[str]:
    """Render pages [start, end) as base64-encoded PNG images."""
    doc = fitz.open(str(pdf_path))
    images: list[str] = []
    try:
        for i in range(start, min(end, len(doc))):
            pix = doc[i].get_pixmap(
                matrix=fitz.Matrix(RENDER_SCALE, RENDER_SCALE), alpha=False
            )
            png_bytes = pix.tobytes("png")
            images.append(base64.b64encode(png_bytes).decode("utf-8"))
    finally:
        doc.close()
    return images


def _extract_with_vision(
    client: OpenAI,
    images_b64: list[str],
    page_label: str,
    exam_hint: str = "",
) -> list[ExtractedQuestion]:
    """Send page images to GPT-4o vision and return extracted questions."""
    hint_text = f"Exam context for these pages:\n{exam_hint}\n\n" if exam_hint else ""
    user_content: list[dict] = [
        {
            "type": "text",
            "text": (
                f"Extract all chemistry MCQ questions from the page images below.\n\n"
                f"{hint_text}"
                "Remember: output Tamil text in Tamil Unicode script, not romanised."
            ),
        }
    ]
    for b64 in images_b64:
        user_content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{b64}",
                    "detail": "high",
                },
            }
        )

    try:
        response = client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format=ExtractedBatch,
            temperature=0,
        )
        batch = response.choices[0].message.parsed
        qs = (batch.questions or []) if batch else []
        print(f"  {page_label}: {len(qs)} question(s) extracted")
        return qs
    except Exception as exc:
        print(f"  {page_label}: Vision API error — {exc}")
        return []


# ─── DB helpers ───────────────────────────────────────────────────────────────

def _save_questions(
    db,
    doc: PyqDocument,
    subject: PyqSubject,
    questions: list[ExtractedQuestion],
) -> int:
    MCQ_SLOTS = 4
    saved = 0
    for q_no, q in enumerate(questions, start=1):
        q_en = (q.question_en or "").strip()
        q_ta = (q.question_ta or "").strip()
        if not q_en and not q_ta:
            continue

        opts_en, opts_ta = _align_mcq_options(q.options_en, q.options_ta)
        filled = sum(1 for i in range(MCQ_SLOTS) if (opts_en[i] or opts_ta[i]).strip())
        if filled < 2:
            continue

        opts_display = _options_display_lines(opts_en, opts_ta)
        correct = (q.correct_answer or "").strip()
        expl = (q.explanation or "").strip()
        exam_val = (q.exam or "").strip() or None
        topic_val = (q.topic or "").strip() or None
        yr = q.year if q.year is not None else doc.year_to
        q_text = _merge_bilingual_text(q_ta, q_en)
        answer_db = _answer_key_for_db(correct, opts_display)

        db.add(
            PyqQuestion(
                document_id=doc.id,
                subject_id=subject.id,
                question_no=q_no,
                question_en=q_en,
                question_ta=q_ta,
                options_en=opts_en,
                options_ta=opts_ta,
                correct_answer=correct,
                explanation=expl,
                year=yr,
                topic=topic_val,
                exam=exam_val,
                question_text_bilingual=q_text,
                options_json=opts_display,
                answer_key=answer_db,
                explanation_bilingual=expl,
                source_page=None,
                parse_confidence=95,
                raw_meta_json={
                    "source": "gpt4o_vision",
                    "question_en": q_en,
                    "question_ta": q_ta,
                    "options_en": opts_en,
                    "options_ta": opts_ta,
                    "correct_answer": correct,
                    "explanation": expl,
                    "exam": exam_val,
                    "year": yr,
                    "topic": topic_val,
                },
            )
        )
        saved += 1

        if saved % 50 == 0:
            db.flush()
            print(f"  → flushed {saved} questions so far…")

    return saved


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    if not (settings.openai_api_key or "").strip():
        print("ERROR: Set OPENAI_API_KEY in backend/.env")
        raise SystemExit(2)

    db = SessionLocal()
    try:
        sync_pyq_catalog_from_files(db)

        subject = db.query(PyqSubject).filter(
            PyqSubject.subject_slug == SUBJECT_SLUG
        ).first()
        if subject is None:
            print(f"Subject '{SUBJECT_SLUG}' not found after catalog sync.")
            raise SystemExit(1)

        doc = (
            db.query(PyqDocument)
            .filter(PyqDocument.subject_id == subject.id)
            .order_by(PyqDocument.created_at.asc())
            .first()
        )
        if doc is None:
            print("No PyqDocument row found for chemistry.")
            raise SystemExit(1)

        if not CHEMISTRY_PDF.is_file():
            print(f"PDF not found: {CHEMISTRY_PDF}")
            raise SystemExit(1)

        # Clear existing
        deleted = (
            db.query(PyqQuestion)
            .filter(PyqQuestion.subject_id == subject.id)
            .delete(synchronize_session=False)
        )
        doc.total_questions = 0
        doc.status = PyqIngestStatus.PENDING
        db.commit()
        print(f"Cleared {deleted} existing question(s). Starting GPT-4o vision extraction.")

        pdf_doc = fitz.open(str(CHEMISTRY_PDF))
        total_pages = len(pdf_doc)
        pdf_doc.close()
        print(f"PDF: {CHEMISTRY_PDF.name}  ({total_pages} pages, {PAGES_PER_BATCH} pages/batch)")

        client = OpenAI(api_key=settings.openai_api_key)
        page_exam_map = _build_page_exam_map(CHEMISTRY_PDF)
        print(f"Watermark map: {len(page_exam_map)} pages have exam/year info")

        all_questions: list[ExtractedQuestion] = []

        for start in range(0, total_pages, PAGES_PER_BATCH):
            end = min(start + PAGES_PER_BATCH, total_pages)
            label = f"pages {start + 1}–{end}"
            print(f"Vision extract: {label}…")

            images_b64 = _render_pages_b64(CHEMISTRY_PDF, start, end)
            if not images_b64:
                print(f"  {label}: could not render, skipping")
                continue

            # Build exam hint from watermarks
            exam_contexts = [
                f"Page {pg + 1}: {lbl} ({yr})"
                for pg in range(start, end)
                if pg in page_exam_map
                for lbl, yr in [page_exam_map[pg]]
            ]
            exam_hint = "\n".join(exam_contexts)

            batch_qs = _extract_with_vision(client, images_b64, label, exam_hint=exam_hint)
            all_questions.extend(batch_qs)

            if len(all_questions) >= MAX_QUESTIONS * 2:
                print(f"  Hit {len(all_questions)} candidates — stopping early")
                break

        print(f"\nTotal candidates: {len(all_questions)}")

        # Deduplicate
        seen: set[str] = set()
        unique: list[ExtractedQuestion] = []
        for q in all_questions:
            key = re.sub(r"\s+", " ", f"{q.question_en} {q.question_ta}").strip().lower()[:250]
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(q)
            if len(unique) >= MAX_QUESTIONS:
                break

        print(f"Unique after dedup: {len(unique)}")

        saved = _save_questions(db, doc, subject, unique)
        doc.total_questions = saved
        doc.status = PyqIngestStatus.INGESTED if saved else PyqIngestStatus.FAILED
        db.commit()

        print(f"\n✓ Done — saved {saved} chemistry PYQ questions to DB.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
