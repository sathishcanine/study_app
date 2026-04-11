import hashlib
import io
import logging
import re
import time
from pathlib import Path

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from pypdf import PdfReader
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import PyqDocument, PyqIngestStatus, PyqQuestion, PyqSubject
from app.schemas import PyqManualQuestionIn

PREVIOUS_YEAR_DIR = Path(__file__).resolve().parents[1] / "data" / "previous_year"
logger = logging.getLogger("uvicorn.error")

_OPTION_RE = re.compile(r"^\s*[\(\[]?([A-D])[)\].\-:]\s*(.+?)\s*$", re.IGNORECASE)
_QUESTION_RE = re.compile(r"^\s*(\d{1,3})[\).\-:]\s+(.+)$")
_YEAR_RANGE_RE = re.compile(r"(20\d{2})\D+(20\d{2})")
_SINGLE_YEAR_RE = re.compile(r"(20\d{2})")
_PAGE_RANGE_TRAIL_RE = re.compile(r"\d+\s*[-–—]\s*\d+\s*$")

_SUBJECT_SYNONYMS: dict[str, str] = {
    "bio": "biology",
    "biology": "biology",
    "chemistry": "chemistry",
    "chem": "chemistry",
    "physics": "physics",
    "indian_polity": "indian_polity",
    "polity": "indian_polity",
    "indian_history": "indian_history",
    "history": "indian_history",
    "indian_economy": "indian_economy",
    "economy": "indian_economy",
    "inm": "indian_national_movement",
    "indian_national_movement": "indian_national_movement",
    "tamil_society": "tamil_society",
    "thirukural": "thirukural",
    "tn_administration": "tn_administration",
}


class LlmPyqQuestion(BaseModel):
    """OpenAI structured output aligned with the app's PYQ JSON contract."""

    question_en: str = ""
    question_ta: str = ""
    options_en: list[str] = Field(default_factory=list)
    options_ta: list[str] = Field(default_factory=list)
    correct_answer: str = ""
    explanation: str = ""
    exam: str | None = None
    year: int | None = None
    topic: str | None = None


class LlmPyqBatch(BaseModel):
    questions: list[LlmPyqQuestion]


_MCQ_SLOTS = 4


def _strip_option_prefix(s: str) -> str:
    return re.sub(r"^\s*[\(\[]?([A-D])[)\].\-:]\s*", "", (s or "").strip(), flags=re.IGNORECASE).strip()


def _align_mcq_options(options_en: list[str], options_ta: list[str]) -> tuple[list[str], list[str]]:
    """
    Normalize to four A–D slots. Missing Tamil text uses English for that index; missing English uses Tamil.
    """
    en = [_strip_option_prefix(x) for x in (options_en or [])[:_MCQ_SLOTS]]
    ta = [_strip_option_prefix(x) for x in (options_ta or [])[:_MCQ_SLOTS]]
    while len(en) < _MCQ_SLOTS:
        en.append("")
    while len(ta) < _MCQ_SLOTS:
        ta.append("")
    for i in range(_MCQ_SLOTS):
        if not ta[i].strip() and en[i].strip():
            ta[i] = en[i]
        if not en[i].strip() and ta[i].strip():
            en[i] = ta[i]
    return en, ta


def _options_display_lines(options_en: list[str], options_ta: list[str]) -> list[str]:
    """Legacy `options_json`: one line per choice with A–D label."""
    letters = ("A", "B", "C", "D")
    out: list[str] = []
    for i in range(_MCQ_SLOTS):
        e = (options_en[i] or "").strip()
        t = (options_ta[i] or "").strip()
        body = f"{t} | {e}" if t and e and t != e else (t or e)
        if not body:
            continue
        out.append(f"{letters[i]}. {body}")
    return out


def _to_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return re.sub(r"_+", "_", slug).strip("_")


def _to_name_from_slug(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.split("_"))


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _extract_year_range(file_name: str) -> tuple[int | None, int | None]:
    m = _YEAR_RANGE_RE.search(file_name)
    if m:
        y1, y2 = int(m.group(1)), int(m.group(2))
        return (y1, y2) if y1 <= y2 else (y2, y1)
    years = [int(y) for y in _SINGLE_YEAR_RE.findall(file_name)]
    if not years:
        return None, None
    return min(years), max(years)


def _extract_subject_from_filename(file_name: str) -> str:
    stem = Path(file_name).stem
    stem = stem.replace("PDF", " ").replace("PYQ", " ").replace("QUESTION", " ")
    stem = re.sub(r"20\d{2}\D+20\d{2}", "", stem)
    stem = re.sub(r"20\d{2}", "", stem)
    stem = re.sub(r"[-_]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    slug = _to_slug(stem)
    if slug in _SUBJECT_SYNONYMS:
        return _SUBJECT_SYNONYMS[slug]
    for key, mapped in _SUBJECT_SYNONYMS.items():
        if key in slug:
            return mapped
    return slug


def _canonical_file_name(path: Path, subject_slug: str, year_from: int | None, year_to: int | None) -> str:
    if year_from is not None and year_to is not None:
        return f"{subject_slug}__pyq__{year_from}_{year_to}.pdf"
    if year_to is not None:
        return f"{subject_slug}__pyq__{year_to}.pdf"
    return f"{subject_slug}__pyq.pdf"


def _normalize_filename(path: Path, subject_slug: str, year_from: int | None, year_to: int | None) -> Path:
    target_name = _canonical_file_name(path, subject_slug, year_from, year_to)
    if path.name == target_name:
        return path
    target = path.with_name(target_name)
    counter = 1
    while target.exists():
        target = path.with_name(target_name.replace(".pdf", f"_{counter}.pdf"))
        counter += 1
    path.rename(target)
    return target


def _extract_text_pypdf(path: Path) -> str:
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _extract_text_with_ocr(path: Path) -> str:
    try:
        import fitz  # type: ignore
        from PIL import Image  # type: ignore
        import pytesseract  # type: ignore
    except Exception:
        return ""
    pages: list[str] = []
    doc = fitz.open(str(path))
    try:
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            img_bytes = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_bytes))
            text = pytesseract.image_to_string(image, lang="eng+tam")
            pages.append(text or "")
    finally:
        doc.close()
    return "\n".join(pages)


def _extract_text_hybrid(path: Path) -> tuple[str, str, list[dict]]:
    text_pdf = _extract_text_pypdf(path)
    text_ocr = _extract_text_with_ocr(path)
    parsed_pdf = _extract_questions(text_pdf)
    parsed_ocr = _extract_questions(text_ocr) if text_ocr.strip() else []
    if len(parsed_ocr) > len(parsed_pdf):
        return text_ocr, "ocr", parsed_ocr
    if parsed_pdf:
        return text_pdf, "pypdf", parsed_pdf
    if text_ocr.strip():
        return text_ocr, "hybrid_fallback", parsed_ocr
    return text_pdf, "pypdf_empty", parsed_pdf


def _llm() -> ChatOpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is missing in backend/.env")
    return ChatOpenAI(model=settings.llm_model, api_key=settings.openai_api_key, temperature=0.0)


def _split_for_llm(raw_text: str, chunk_size: int = 12000) -> list[str]:
    text = raw_text.strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end
    return chunks


def _pdf_page_count(path: Path) -> int:
    try:
        import fitz  # type: ignore

        doc = fitz.open(str(path))
        try:
            return len(doc)
        finally:
            doc.close()
    except Exception:
        reader = PdfReader(str(path))
        return len(reader.pages)


def _pypdf_page_range(path: Path, start: int, end: int) -> str:
    reader = PdfReader(str(path))
    end = min(end, len(reader.pages))
    parts: list[str] = []
    for i in range(start, end):
        parts.append(reader.pages[i].extract_text() or "")
    return "\n".join(parts)


def _ocr_page_range(path: Path, start: int, end: int) -> str:
    try:
        import fitz  # type: ignore
        from PIL import Image  # type: ignore
        import pytesseract  # type: ignore
    except Exception:
        return ""
    doc = fitz.open(str(path))
    try:
        end = min(end, len(doc))
        pages: list[str] = []
        for i in range(start, end):
            page = doc[i]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            img_bytes = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_bytes))
            pages.append(pytesseract.image_to_string(image, lang="eng+tam") or "")
        return "\n".join(pages)
    finally:
        doc.close()


def _text_for_page_batch(path: Path, start: int, end: int) -> tuple[str, str]:
    """Return (text, source) for pages [start, end). Prefer pypdf if batch has enough text."""
    pdf_text = _pypdf_page_range(path, start, end)
    non_empty = len([ln for ln in pdf_text.splitlines() if ln.strip()])
    if non_empty > 30 and len(pdf_text.strip()) > 400:
        return pdf_text, "pypdf"
    ocr_text = _ocr_page_range(path, start, end)
    if len(ocr_text.strip()) > len(pdf_text.strip()):
        return ocr_text, "ocr"
    return pdf_text, "pypdf_fallback"


def _max_pages_for_openai(max_questions: int, total_pages: int) -> int:
    """Avoid OCR'ing 400+ pages when only a small sample is needed."""
    if max_questions <= 30:
        return min(total_pages, max(50, max_questions * 5))
    if max_questions <= 120:
        return min(total_pages, max(120, max_questions * 3))
    return total_pages


def _merge_bilingual_text(ta: str, en: str) -> str:
    ta_clean = (ta or "").strip()
    en_clean = (en or "").strip()
    if ta_clean and en_clean:
        return f"{ta_clean}\n\n{en_clean}"
    return ta_clean or en_clean


def _merge_bilingual_options(ta_opts: list[str], en_opts: list[str]) -> list[str]:
    size = max(len(ta_opts), len(en_opts))
    out: list[str] = []
    for i in range(size):
        ta = ta_opts[i].strip() if i < len(ta_opts) else ""
        en = en_opts[i].strip() if i < len(en_opts) else ""
        if ta and en:
            out.append(f"{ta} | {en}")
        else:
            out.append(ta or en)
    return [o for o in out if o]


def _answer_key_for_db(answer: str, options: list[str]) -> str:
    """
    DB column `answer_key` is VARCHAR(30). Store a short key; full wording is in `correct_answer`.
    Prefer matching option letter (A-D) when possible.
    """
    a = (answer or "").strip()
    if not a:
        return ""
    m = re.match(r"^\(?\s*([A-E])\s*\)?[\).:\s]", a, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    al = re.sub(r"\s+", " ", a).lower()
    for i, opt in enumerate(options):
        ol = re.sub(r"\s+", " ", (opt or "").strip()).lower()
        if not ol:
            continue
        if al == ol or al in ol or ol in al:
            return chr(65 + i) if i < 5 else str(i + 1)
    return a[:30]


def _first_pyq_document(db: Session, subject_id) -> PyqDocument | None:
    return (
        db.query(PyqDocument)
        .filter(PyqDocument.subject_id == subject_id)
        .order_by(PyqDocument.created_at.asc())
        .first()
    )


def _persist_llm_question_row(
    db: Session,
    *,
    doc: PyqDocument,
    subject_id,
    q: LlmPyqQuestion,
    question_no: int,
    source_token: str,
) -> bool:
    q_en = (q.question_en or "").strip()
    q_ta = (q.question_ta or "").strip()
    if not q_en and not q_ta:
        return False
    opts_en, opts_ta = _align_mcq_options(q.options_en, q.options_ta)
    filled = sum(1 for i in range(_MCQ_SLOTS) if (opts_en[i] or opts_ta[i]).strip())
    if filled < 2:
        return False
    q_text = _merge_bilingual_text(q_ta, q_en)
    opts_display = _options_display_lines(opts_en, opts_ta)
    if len(opts_display) < 2:
        return False
    correct = (q.correct_answer or "").strip()
    if not correct:
        return False
    answer_db = _answer_key_for_db(correct, opts_display)
    expl = (q.explanation or "").strip()
    exam_val = (q.exam or "").strip() or None
    topic_val = (q.topic or "").strip() or None
    yr = q.year if q.year is not None else doc.year_to
    db.add(
        PyqQuestion(
            document_id=doc.id,
            subject_id=subject_id,
            question_no=question_no,
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
            parse_confidence=90,
            raw_meta_json={
                "source": source_token,
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
    return True


def _refresh_doc_question_count(db: Session, doc: PyqDocument) -> None:
    n = (
        db.query(func.count(PyqQuestion.id))
        .filter(PyqQuestion.document_id == doc.id)
        .scalar()
        or 0
    )
    doc.total_questions = int(n)
    doc.status = PyqIngestStatus.INGESTED if n else PyqIngestStatus.PENDING


def _refresh_all_doc_counts_for_subject(db: Session, subject_id) -> None:
    for d in db.query(PyqDocument).filter(PyqDocument.subject_id == subject_id).all():
        _refresh_doc_question_count(db, d)


def import_pyq_manual_json(
    db: Session,
    *,
    subject_slug: str,
    rows: list[PyqManualQuestionIn],
    replace_subject_questions: bool = False,
) -> dict:
    """
    Insert questions from a JSON list (e.g. typed from ChatGPT output).
    Rows attach to the subject's first PYQ document (same file row as catalog).
    """
    subject_key = (subject_slug or "").strip().lower()
    if not subject_key:
        raise RuntimeError("subject_slug is required")
    subject = db.query(PyqSubject).filter(PyqSubject.subject_slug == subject_key).first()
    if subject is None:
        raise RuntimeError(f"Subject not found: {subject_key}")
    doc = _first_pyq_document(db, subject.id)
    if doc is None:
        raise RuntimeError(f"No PYQ document row for subject {subject_key}; sync catalog first")

    if replace_subject_questions:
        db.query(PyqQuestion).filter(PyqQuestion.subject_id == subject.id).delete()
        db.flush()
        start_no = 1
    else:
        m = db.query(func.max(PyqQuestion.question_no)).filter(PyqQuestion.subject_id == subject.id).scalar()
        start_no = (int(m) if m is not None else 0) + 1

    inserted = 0
    no = start_no
    for row in rows:
        ans = (row.answer or "").strip()
        if not ans:
            continue
        q_en = (row.question_en or row.question_text or "").strip()
        q_ta = (row.question_ta or "").strip()
        if not q_en and not q_ta:
            continue
        base_opts = [o.strip() for o in row.options if (o or "").strip()]
        oen = [o.strip() for o in (row.options_en or []) if (o or "").strip()] or base_opts
        ota = [o.strip() for o in (row.options_ta or []) if (o or "").strip()]
        opts_en, opts_ta = _align_mcq_options(oen, ota)
        if sum(1 for i in range(_MCQ_SLOTS) if (opts_en[i] or opts_ta[i]).strip()) < 2:
            continue
        opts_display = _options_display_lines(opts_en, opts_ta)
        expl = (row.explanation or "").strip()
        topic_val = (row.topic or row.subtopic or "").strip() or None
        exam_val = (row.exam or row.exam_name or "").strip() or None
        yr = row.year if row.year is not None else doc.year_to
        q_bilingual = _merge_bilingual_text(q_ta, q_en)
        answer_db = _answer_key_for_db(ans, opts_display)
        db.add(
            PyqQuestion(
                document_id=doc.id,
                subject_id=subject.id,
                question_no=no,
                question_en=q_en,
                question_ta=q_ta,
                options_en=opts_en,
                options_ta=opts_ta,
                correct_answer=ans,
                explanation=expl,
                year=yr,
                topic=topic_val,
                exam=exam_val,
                question_text_bilingual=q_bilingual,
                options_json=opts_display,
                answer_key=answer_db,
                explanation_bilingual=expl,
                source_page=None,
                parse_confidence=100,
                raw_meta_json={"source": "openai_manual_json", "correct_answer": ans},
            )
        )
        inserted += 1
        no += 1

    _refresh_all_doc_counts_for_subject(db, subject.id)
    db.commit()
    return {
        "subject_slug": subject_key,
        "questions_inserted": inserted,
        "replace_subject_questions": replace_subject_questions,
        "starting_question_no": start_no,
    }


def ingest_pasted_text_with_openai(
    db: Session,
    *,
    subject_slug: str,
    raw_text: str,
    append: bool = True,
    max_questions: int = 40,
) -> dict:
    """
    Parse pasted notes / ChatGPT-style text with the same structured LLM as PDF ingest,
    then save rows (append or replace all questions for the subject).
    """
    subject_key = (subject_slug or "").strip().lower()
    if not subject_key:
        raise RuntimeError("subject_slug is required")
    subject = db.query(PyqSubject).filter(PyqSubject.subject_slug == subject_key).first()
    if subject is None:
        raise RuntimeError(f"Subject not found: {subject_key}")
    doc = _first_pyq_document(db, subject.id)
    if doc is None:
        raise RuntimeError(f"No PYQ document row for subject {subject_key}; sync catalog first")

    text = (raw_text or "").strip()
    if len(text) < 20:
        raise RuntimeError("raw_text is too short")

    if not append:
        db.query(PyqQuestion).filter(PyqQuestion.subject_id == subject.id).delete()
        db.flush()
        start_no = 1
    else:
        m = db.query(func.max(PyqQuestion.question_no)).filter(PyqQuestion.subject_id == subject.id).scalar()
        start_no = (int(m) if m is not None else 0) + 1

    llm = _llm()
    parser = llm.with_structured_output(LlmPyqBatch)
    collected: list[LlmPyqQuestion] = []
    for part in _split_for_llm(text, chunk_size=12000):
        prompt = (
            "The user pasted TNPSC previous-year style questions (from ChatGPT, notes, or a PDF excerpt).\n"
            "Extract every distinct multiple-choice question into the structured fields.\n"
            "Use question_en / options_en when the paste is English; use question_ta / options_ta for Tamil; fill both when bilingual.\n"
            "options_en and options_ta must be four choice texts in order (A–D), without the A/B/C/D prefix when possible.\n"
            "correct_answer should match one option (e.g. \"C. Urea\" or a single letter if that is all that is printed).\n"
            "Set year, exam (e.g. \"Group 1 2023\"), and topic when stated or clearly implied.\n"
            "Ignore chat boilerplate, separators, and numbering that is not part of the exam item.\n\n"
            f"Pasted text:\n{part}"
        )
        out = parser.invoke(prompt)
        collected.extend(out.questions or [])

    seen: set[str] = set()
    kept: list[LlmPyqQuestion] = []
    for q in collected:
        key = re.sub(r"\s+", " ", f"{q.question_ta} {q.question_en}").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append(q)
        if len(kept) >= max_questions:
            break

    inserted = 0
    no = start_no
    for q in kept:
        if _persist_llm_question_row(
            db,
            doc=doc,
            subject_id=subject.id,
            q=q,
            question_no=no,
            source_token="openai_paste",
        ):
            inserted += 1
            no += 1

    _refresh_all_doc_counts_for_subject(db, subject.id)
    db.commit()
    return {
        "subject_slug": subject_key,
        "questions_inserted": inserted,
        "append": append,
        "max_questions": max_questions,
        "candidates_seen": len(kept),
    }


def _extract_questions(raw_text: str) -> list[dict]:
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    out: list[dict] = []
    current: dict | None = None

    def _is_probable_toc_header(line: str) -> bool:
        l = line.upper()
        return ("INDEX" in l) or ("TOPIC NAME" in l) or ("PAGE NO" in l)

    def _is_probable_toc_row(text: str) -> bool:
        upper = text.upper()
        if "TOPIC" in upper and "PAGE" in upper:
            return True
        if _PAGE_RANGE_TRAIL_RE.search(text) and "?" not in text:
            return True
        return False

    def _is_valid_question_candidate(item: dict) -> bool:
        txt = (item.get("question_text_bilingual") or "").strip()
        opts = item.get("options") or []
        if not txt:
            return False
        if _is_probable_toc_row(txt):
            return False
        if len(opts) >= 2:
            return True
        return "?" in txt

    for line in lines:
        if _is_probable_toc_header(line):
            continue
        q = _QUESTION_RE.match(line)
        if q:
            if current is not None and _is_valid_question_candidate(current):
                out.append(current)
            current = {
                "question_no": int(q.group(1)),
                "question_text_bilingual": q.group(2).strip(),
                "options": [],
                "answer_key": "",
                "explanation_bilingual": "",
                "parse_confidence": 30,
            }
            continue
        if current is None:
            continue
        o = _OPTION_RE.match(line)
        if o and len(current["options"]) < 6:
            current["options"].append(line)
            current["parse_confidence"] = 65
            continue
        if line.lower().startswith(("answer", "ans")):
            current["answer_key"] = line.split(":", 1)[-1].strip() if ":" in line else line
            current["parse_confidence"] = max(current["parse_confidence"], 75)
            continue
        if len(current["question_text_bilingual"]) < 3000:
            current["question_text_bilingual"] += f"\n{line}"
    if current is not None and _is_valid_question_candidate(current):
        out.append(current)
    return out


def ingest_previous_year_documents(db: Session, subject_slug_filter: str | None = None) -> dict:
    PREVIOUS_YEAR_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(PREVIOUS_YEAR_DIR.glob("*.pdf"))
    files_seen = 0
    documents_synced = 0
    questions_upserted = 0
    renamed_files = 0
    ocr_used_files = 0
    failed_files = 0
    started_at = time.perf_counter()
    logger.info(
        "PYQ ingest started (filter=%s, dir=%s, files=%s)",
        subject_slug_filter or "all",
        PREVIOUS_YEAR_DIR,
        len(files),
    )

    for path in files:
        file_started = time.perf_counter()
        files_seen += 1
        original_name = path.name
        subject_slug = _extract_subject_from_filename(path.name)
        if not subject_slug:
            subject_slug = "general"
        if subject_slug_filter and subject_slug != subject_slug_filter:
            continue
        subject_name = _to_name_from_slug(subject_slug)
        year_from, year_to = _extract_year_range(path.name)
        normalized_path = _normalize_filename(path, subject_slug, year_from, year_to)
        if normalized_path != path:
            renamed_files += 1
            logger.info("PYQ file renamed: %s -> %s", original_name, normalized_path.name)
        path = normalized_path
        file_hash = _checksum(path)

        subject = db.query(PyqSubject).filter(PyqSubject.subject_slug == subject_slug).first()
        if not subject:
            subject = PyqSubject(subject_slug=subject_slug, subject_name=subject_name)
            db.add(subject)
            db.flush()

        doc = db.query(PyqDocument).filter(PyqDocument.file_path == str(path)).first()
        if not doc:
            doc = PyqDocument(
                subject_id=subject.id,
                file_name=path.name,
                file_path=str(path),
                checksum=file_hash,
                year_from=year_from,
                year_to=year_to,
                status=PyqIngestStatus.PENDING,
            )
            db.add(doc)
            db.flush()
        else:
            if doc.checksum == file_hash and doc.status == PyqIngestStatus.INGESTED:
                # For focused debugging runs (subject filter), force re-parse if previous extraction
                # looks too low. This helps recover from earlier bad parsing (e.g. TOC-only rows).
                if subject_slug_filter and int(doc.total_questions or 0) < 150:
                    logger.info(
                        "PYQ file marked for reprocess (low prior count): %s subject=%s total_questions=%s",
                        path.name,
                        subject_slug,
                        doc.total_questions,
                    )
                else:
                    documents_synced += 1
                    logger.info(
                        "PYQ file skipped (unchanged): %s subject=%s total_questions=%s",
                        path.name,
                        subject_slug,
                        doc.total_questions,
                    )
                    continue
            doc.subject_id = subject.id
            doc.file_name = path.name
            doc.checksum = file_hash
            doc.year_from = year_from
            doc.year_to = year_to
            db.query(PyqQuestion).filter(PyqQuestion.document_id == doc.id).delete()

        try:
            text, source, parsed = _extract_text_hybrid(path)
            if source == "ocr":
                ocr_used_files += 1
            if not parsed:
                doc.total_questions = 0
                doc.status = PyqIngestStatus.FAILED
                failed_files += 1
                logger.warning(
                    "PYQ parse failed: %s subject=%s source=%s chars=%s",
                    path.name,
                    subject_slug,
                    source,
                    len(text),
                )
                continue
            for item in parsed:
                q_body = (item.get("question_text_bilingual") or "").strip()
                opt_lines = item.get("options") or []
                opt_bodies: list[str] = []
                for line in opt_lines:
                    m = _OPTION_RE.match(str(line))
                    if m:
                        opt_bodies.append(m.group(2).strip())
                    else:
                        opt_bodies.append(_strip_option_prefix(str(line)))
                opts_en, opts_ta = _align_mcq_options(opt_bodies, [])
                opts_display = _options_display_lines(opts_en, opts_ta)
                raw_ans = str(item.get("answer_key") or "").strip()
                expl = (item.get("explanation_bilingual") or "").strip()
                answer_db = _answer_key_for_db(raw_ans, opts_display)
                q = PyqQuestion(
                    document_id=doc.id,
                    subject_id=subject.id,
                    question_no=item["question_no"],
                    question_en=q_body,
                    question_ta="",
                    options_en=opts_en,
                    options_ta=opts_ta,
                    correct_answer=raw_ans,
                    explanation=expl,
                    year=year_to,
                    topic=None,
                    exam=None,
                    question_text_bilingual=q_body,
                    options_json=opts_display if opts_display else list(opt_lines),
                    answer_key=answer_db,
                    explanation_bilingual=expl,
                    source_page=None,
                    parse_confidence=item["parse_confidence"],
                    raw_meta_json={"source": source},
                )
                db.add(q)
            doc.total_questions = len(parsed)
            doc.status = PyqIngestStatus.INGESTED
            questions_upserted += len(parsed)
            logger.info(
                "PYQ file ingested: %s subject=%s source=%s questions=%s duration_ms=%s",
                path.name,
                subject_slug,
                source,
                len(parsed),
                int((time.perf_counter() - file_started) * 1000),
            )
        except Exception:
            doc.total_questions = 0
            doc.status = PyqIngestStatus.FAILED
            failed_files += 1
            logger.exception("PYQ ingest exception for file: %s", path.name)

        documents_synced += 1

    db.commit()
    summary = {
        "files_seen": files_seen,
        "documents_synced": documents_synced,
        "questions_upserted": questions_upserted,
        "renamed_files": renamed_files,
        "ocr_used_files": ocr_used_files,
        "failed_files": failed_files,
        "duration_ms": int((time.perf_counter() - started_at) * 1000),
        "data_dir": str(PREVIOUS_YEAR_DIR),
    }
    logger.info("PYQ ingest finished: %s", summary)
    return summary


def ingest_subject_with_openai(db: Session, subject_slug: str, max_questions: int = 450) -> dict:
    """
    High-quality OpenAI extraction for one subject PDF.
    Persists bilingual columns (question_en/ta, options_en/ta, correct_answer, explanation, exam, year, topic)
    plus legacy combined fields for older clients.
    """
    subject_key = (subject_slug or "").strip().lower()
    if not subject_key:
        raise RuntimeError("subject_slug is required")

    subject = db.query(PyqSubject).filter(PyqSubject.subject_slug == subject_key).first()
    if subject is None:
        raise RuntimeError(f"Subject not found: {subject_key}")

    docs = db.query(PyqDocument).filter(PyqDocument.subject_id == subject.id).all()
    if not docs:
        raise RuntimeError(f"No PYQ documents found for subject: {subject_key}")

    # Remove all prior rows (including noisy OCR) so this subject only shows OpenAI output.
    db.query(PyqQuestion).filter(PyqQuestion.subject_id == subject.id).delete()
    db.flush()

    llm = _llm()
    parser = llm.with_structured_output(LlmPyqBatch)

    total_upserted = 0
    chunks_processed = 0
    for doc in docs:
        path = Path(doc.file_path)
        if not path.is_file():
            doc.status = PyqIngestStatus.FAILED
            doc.total_questions = 0
            continue

        total_pages = _pdf_page_count(path)
        pages_cap = _max_pages_for_openai(max_questions, total_pages)
        batch_size = 6 if max_questions <= 40 else 10
        # Skip early pages (often index/TOC) when extracting a small sample only.
        if max_questions <= 40:
            start_offset = min(22, max(0, total_pages - 1))
            scan_end = min(total_pages, start_offset + 72)
        else:
            start_offset = 0
            scan_end = pages_cap
        collected: list[LlmPyqQuestion] = []
        last_source = "pypdf"
        batch_idx = 0
        seen_quick: set[str] = set()
        for start in range(start_offset, scan_end, batch_size):
            if len(collected) >= max_questions * 3:
                break
            end = min(start + batch_size, scan_end)
            raw_text, batch_source = _text_for_page_batch(path, start, end)
            last_source = batch_source
            if not raw_text.strip():
                continue
            for part in _split_for_llm(raw_text, chunk_size=10000):
                if len(collected) >= max_questions * 3:
                    break
                chunks_processed += 1
                batch_idx += 1
                prompt = (
                    "You are extracting TNPSC previous-year questions from OCR/PDF text.\n"
                    "Return only real exam questions from this chunk.\n"
                    "Ignore index pages, topic tables, headers, watermarks, and junk OCR lines.\n"
                    "For each question, capture Tamil and English when both appear; if only one language, leave the other language fields empty.\n"
                    "\n"
                    "OPTIONS vs STEM (critical):\n"
                    "- options_en and options_ta must each be an array of exactly four strings (choices A–D in order). "
                    "Values are the choice text only (no \"A.\" prefix).\n"
                    "- If a language column is missing in the source for a given choice, output an empty string for that index; "
                    "the pipeline will cross-fill from the other language.\n"
                    "- Do NOT put roman-numeral sub-parts (i), (ii), (iii)… into options_* unless they are truly the A–D choices.\n"
                    "- If the item has no real A–D block, skip it rather than inventing options.\n"
                    "\n"
                    "ANSWERS:\n"
                    "- correct_answer: prefer \"C. <matching option wording>\" or a single letter if that is all the key shows.\n"
                    "\n"
                    "METADATA (when inferable):\n"
                    "- year: integer exam year (e.g. 2023).\n"
                    "- exam: short label with year, e.g. \"Group 1 2023\", \"CCSE-1 2024\".\n"
                    "- topic: concise subject line, e.g. \"Periodic table\", \"Acids and bases\".\n"
                    "- explanation: official solution or brief rationale when present in the text; else empty string.\n"
                    "\n"
                    f"Pages ~{start + 1}-{end}, part {batch_idx}:\n{part}"
                )
                out = parser.invoke(prompt)
                collected.extend(out.questions or [])
                for q in out.questions or []:
                    k = re.sub(r"\s+", " ", f"{q.question_ta} {q.question_en}").strip().lower()
                    if k:
                        seen_quick.add(k)
                if len(seen_quick) >= max_questions * 2:
                    break
            if len(seen_quick) >= max_questions * 2:
                break

        seen: set[str] = set()
        kept: list[LlmPyqQuestion] = []
        for q in collected:
            key = re.sub(r"\s+", " ", f"{q.question_ta} {q.question_en}").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            kept.append(q)
            if len(kept) >= max_questions:
                break

        saved = 0
        q_no = 1
        for q in kept:
            if _persist_llm_question_row(
                db,
                doc=doc,
                subject_id=subject.id,
                q=q,
                question_no=q_no,
                source_token=f"openai_{last_source}",
            ):
                saved += 1
                q_no += 1
                total_upserted += 1

        doc.total_questions = saved
        doc.status = PyqIngestStatus.INGESTED if saved else PyqIngestStatus.FAILED
        logger.info(
            "PYQ OpenAI ingested: file=%s subject=%s questions_saved=%s candidates=%s pages_range=%s-%s source=%s",
            path.name,
            subject_key,
            saved,
            len(kept),
            start_offset,
            scan_end,
            last_source,
        )

    db.commit()
    summary = {
        "subject_slug": subject_key,
        "questions_upserted": total_upserted,
        "chunks_processed": chunks_processed,
        "max_questions": max_questions,
    }
    logger.info("PYQ OpenAI ingest finished: %s", summary)
    return summary


def sync_pyq_catalog_from_files(db: Session) -> dict:
    """
    Lightweight sync that creates subject/document rows from filenames only.
    Does not parse question content. Useful to populate PYQ subject grid quickly.
    """
    PREVIOUS_YEAR_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(PREVIOUS_YEAR_DIR.glob("*.pdf"))
    subjects_created = 0
    documents_created = 0
    renamed_files = 0
    started_at = time.perf_counter()
    logger.info("PYQ catalog sync started (dir=%s, files=%s)", PREVIOUS_YEAR_DIR, len(files))

    for path in files:
        subject_slug = _extract_subject_from_filename(path.name) or "general"
        subject_name = _to_name_from_slug(subject_slug)
        year_from, year_to = _extract_year_range(path.name)
        normalized_path = _normalize_filename(path, subject_slug, year_from, year_to)
        if normalized_path != path:
            renamed_files += 1
            logger.info("PYQ catalog rename: %s -> %s", path.name, normalized_path.name)
        path = normalized_path

        subject = db.query(PyqSubject).filter(PyqSubject.subject_slug == subject_slug).first()
        if not subject:
            subject = PyqSubject(subject_slug=subject_slug, subject_name=subject_name)
            db.add(subject)
            db.flush()
            subjects_created += 1

        existing_doc = db.query(PyqDocument).filter(PyqDocument.file_path == str(path)).first()
        if existing_doc:
            continue
        db.add(
            PyqDocument(
                subject_id=subject.id,
                file_name=path.name,
                file_path=str(path),
                checksum=_checksum(path),
                year_from=year_from,
                year_to=year_to,
                status=PyqIngestStatus.PENDING,
                total_questions=0,
            )
        )
        documents_created += 1

    db.commit()
    summary = {
        "files_seen": len(files),
        "subjects_created": subjects_created,
        "documents_created": documents_created,
        "renamed_files": renamed_files,
        "duration_ms": int((time.perf_counter() - started_at) * 1000),
        "data_dir": str(PREVIOUS_YEAR_DIR),
    }
    logger.info("PYQ catalog sync finished: %s", summary)
    return summary
