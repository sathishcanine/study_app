"""
Topic-wise bilingual question generation pipeline.

Folder convention:
  data/topics/<topic_slug>/en/   ← English material PDFs
  data/topics/<topic_slug>/ta/   ← Tamil material PDFs
  data/topics/<topic_slug>/pyq/  ← PYQ PDF (contains both EN + TA questions)

For each question slot the pipeline:
  1. Retrieves EN material + PYQ context  → generates English Q&A
  2. Retrieves TA material + PYQ context  → generates Tamil Q&A (independent, not just translation)
  3. Creates a QuestionPattern (shared ID) and stores both in separate tables.
"""

import hashlib
import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel, Field
from pypdf import PdfReader
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    ExamBlueprint,
    ExamSubjectBlueprint,
    JobStatus,
    QuestionPattern,
    TopicGenerationJob,
    TopicQuestionEn,
    TopicQuestionTa,
    TopicSetInfo,
    TopicSourceChunk,
    TopicSourceKind,
)

SUPPORTED_EXT = {".pdf", ".txt", ".md"}
TOPICS_ROOT = "data/topics"


# ── Pydantic output schemas for LLM structured output ───────────

class BilingualQuestion(BaseModel):
    question_text: str
    options: list[str] = Field(min_length=4, max_length=4)
    answer: str
    explanation: str = ""
    difficulty: str = "medium"


class BilingualBatch(BaseModel):
    questions: list[BilingualQuestion]


DEFAULT_STYLE_HINTS = {
    "easy": "Direct simple factual or concept questions.",
    "moderate": "Match-the-following / article-to-concept style with moderate reasoning.",
    "hard": "Statement-reason / assertion-reason style with tricky distractors.",
}
DEFAULT_DIFFICULTY_SPLIT = {"easy": 10, "moderate": 20, "hard": 70}
TNPSC_FIXED_SUBJECTS = {
    "general_science",
    "current_affairs",
    "geography",
    "history_and_culture_of_india",
    "indian_polity",
    "indian_economy",
    "indian_national_movement",
    "aptitude_and_mental_ability",
    "tamil_language",
    "english_language",
}


# ── Helpers ──────────────────────────────────────────────────────


def _norm(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def is_valid_subject_for_exam(exam_type: str, subject: str) -> bool:
    """Validate fixed subject lists for known exams."""
    subject_key = _norm(subject)
    if exam_type.upper().startswith("TNPSC"):
        return subject_key in TNPSC_FIXED_SUBJECTS
    return True


def _difficulty_quota(total: int, easy_pct: int, moderate_pct: int, hard_pct: int) -> dict[str, int]:
    pcts = {"easy": easy_pct, "moderate": moderate_pct, "hard": hard_pct}
    total_pct = max(1, sum(pcts.values()))
    scaled = {k: max(1, int(round(v * 100 / total_pct))) for k, v in pcts.items()}
    diff = 100 - sum(scaled.values())
    keys = ["easy", "moderate", "hard"]
    i = 0
    while diff != 0:
        k = keys[i % len(keys)]
        if diff > 0:
            scaled[k] += 1
            diff -= 1
        elif scaled[k] > 1:
            scaled[k] -= 1
            diff += 1
        i += 1

    out = {k: max(1, math.floor(scaled[k] * total / 100)) for k in keys}
    q_diff = total - sum(out.values())
    i = 0
    while q_diff != 0:
        k = keys[i % len(keys)]
        if q_diff > 0:
            out[k] += 1
            q_diff -= 1
        elif out[k] > 1:
            out[k] -= 1
            q_diff += 1
        i += 1
    return out


def _get_or_create_subject_blueprint(db: Session, exam_type: str, subject: str) -> ExamSubjectBlueprint:
    exam_type_key = exam_type.upper().strip()
    subject_key = _norm(subject)
    blueprint = db.query(ExamBlueprint).filter(ExamBlueprint.exam_type == exam_type_key).first()
    if blueprint is None:
        blueprint = ExamBlueprint(exam_type=exam_type_key, is_active=True)
        db.add(blueprint)
        db.flush()

    row = (
        db.query(ExamSubjectBlueprint)
        .filter(
            ExamSubjectBlueprint.blueprint_id == blueprint.id,
            ExamSubjectBlueprint.subject == subject_key,
        )
        .first()
    )
    if row is not None:
        return row

    # User requested same difficulty interpretation for all listed TNPSC subjects.
    style = dict(DEFAULT_STYLE_HINTS)
    row = ExamSubjectBlueprint(
        blueprint_id=blueprint.id,
        subject=subject_key,
        easy_pct=DEFAULT_DIFFICULTY_SPLIT["easy"],
        moderate_pct=DEFAULT_DIFFICULTY_SPLIT["moderate"],
        hard_pct=DEFAULT_DIFFICULTY_SPLIT["hard"],
        style_json=style,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _read_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return path.read_text(encoding="utf-8", errors="ignore")


def _chunks(text: str, size: int = 2000, overlap: int = 250) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    out: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + size)
        out.append(cleaned[start:end])
        if end >= len(cleaned):
            break
        start = end - overlap
    return out


def _embedder() -> OpenAIEmbeddings:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is missing in backend/.env")
    return OpenAIEmbeddings(model=settings.embedding_model, api_key=settings.openai_api_key)


def _llm() -> ChatOpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is missing in backend/.env")
    return ChatOpenAI(model=settings.llm_model, api_key=settings.openai_api_key, temperature=0.3)


def _embed_in_batches(embed: OpenAIEmbeddings, parts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Embed long chunk lists in batches to avoid provider token-per-request limits."""
    vectors: list[list[float]] = []
    for i in range(0, len(parts), batch_size):
        vectors.extend(embed.embed_documents(parts[i : i + batch_size]))
    return vectors


# ── Indexing ─────────────────────────────────────────────────────

@dataclass
class _TopicDoc:
    path: Path
    kind: TopicSourceKind


def _scan_topic_docs(topic_slug: str) -> list[_TopicDoc]:
    root = Path(TOPICS_ROOT) / topic_slug
    mapping = {
        "en": TopicSourceKind.MATERIAL_EN,
        "ta": TopicSourceKind.MATERIAL_TA,
        "pyq": TopicSourceKind.PYQ,
    }
    out: list[_TopicDoc] = []
    for subfolder, kind in mapping.items():
        folder = root / subfolder
        if not folder.exists():
            continue
        for p in folder.rglob("*"):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXT:
                out.append(_TopicDoc(path=p, kind=kind))
    return out


def _delete_stale_chunks(db: Session, topic_slug: str, file_path: str, new_checksum: str) -> bool:
    """Remove chunks for a file if checksum changed. Returns True if re-index needed."""
    existing = (
        db.query(TopicSourceChunk)
        .filter(
            TopicSourceChunk.topic_slug == topic_slug,
            TopicSourceChunk.file_path == file_path,
        )
        .first()
    )
    if existing is None:
        return True
    if existing.file_checksum != new_checksum:
        db.query(TopicSourceChunk).filter(
            TopicSourceChunk.topic_slug == topic_slug,
            TopicSourceChunk.file_path == file_path,
        ).delete()
        return True
    return False


def ensure_topic_indexed(db: Session, topic_slug: str) -> None:
    """Index all docs for a topic. Skips unchanged files."""
    docs = _scan_topic_docs(topic_slug)
    if not docs:
        raise RuntimeError(
            f"No documents found for topic '{topic_slug}'. "
            f"Place PDFs under {TOPICS_ROOT}/{topic_slug}/en/, ta/, pyq/"
        )
    embed = _embedder()
    for doc in docs:
        checksum = _sha256(doc.path)
        needs_index = _delete_stale_chunks(db, topic_slug, str(doc.path), checksum)
        if not needs_index:
            continue
        text = _read_text(doc.path)
        parts = _chunks(text)
        if not parts:
            continue
        vectors = _embed_in_batches(embed, parts, batch_size=24)
        for i, (chunk_text, vec) in enumerate(zip(parts, vectors)):
            db.add(
                TopicSourceChunk(
                    topic_slug=topic_slug,
                    kind=doc.kind,
                    file_path=str(doc.path),
                    file_checksum=checksum,
                    chunk_index=i,
                    content=chunk_text,
                    embedding=vec,
                )
            )
    db.commit()


# ── Retrieval ────────────────────────────────────────────────────

def _retrieve_topic(
    db: Session,
    topic_slug: str,
    query: str,
    kind: TopicSourceKind,
    top_k: int = 10,
) -> list[TopicSourceChunk]:
    embed = _embedder()
    q_vec = embed.embed_query(query)
    return (
        db.query(TopicSourceChunk)
        .filter(
            TopicSourceChunk.topic_slug == topic_slug,
            TopicSourceChunk.kind == kind,
        )
        .order_by(TopicSourceChunk.embedding.cosine_distance(q_vec))
        .limit(top_k)
        .all()
    )


def _build_context(chunks: list[TopicSourceChunk], max_chars: int = 900) -> str:
    return "\n\n".join(c.content[:max_chars] for c in chunks)


# ── Question generation ──────────────────────────────────────────

def _gen_en_questions(
    db: Session,
    exam_type: str,
    subject: str,
    topic_slug: str,
    difficulty: str,
    count: int,
    style_hint: str,
) -> list[BilingualQuestion]:
    llm = _llm()
    mat = _retrieve_topic(db, topic_slug, f"{topic_slug} key concepts and facts", TopicSourceKind.MATERIAL_EN, top_k=12)
    pyq = _retrieve_topic(db, topic_slug, f"{topic_slug} previous year MCQ style and pattern", TopicSourceKind.PYQ, top_k=10)

    context = (
        "[ENGLISH MATERIAL]\n" + _build_context(mat)
        + "\n\n[PREVIOUS YEAR QUESTIONS - ENGLISH STYLE]\n" + _build_context(pyq)
    )
    if not context.strip():
        raise RuntimeError(
            f"No indexed English/PYQ content for topic '{topic_slug}'. "
            "Add PDFs to en/ and pyq/ folders."
        )

    parser = llm.with_structured_output(BilingualBatch)
    prompt = (
        f"You are an exam setter for {exam_type}. Generate exactly {count} fresh MCQ questions "
        f"for subject '{subject}', topic '{topic_slug}' in English. "
        f"Difficulty bucket: {difficulty}. "
        f"Difficulty behavior: {style_hint} "
        "Rules: 4 options each, answer must be one of the options, "
        "follow exam style shown in PYQ context, "
        "do NOT copy exact questions from PYQ. "
        "Return JSON only.\n\n"
        f"Context:\n{context}"
    )
    out = parser.invoke(prompt)
    qs = out.questions[:count]
    for q in qs:
        q.difficulty = difficulty
    return qs


def _gen_ta_questions(
    db: Session,
    exam_type: str,
    subject: str,
    topic_slug: str,
    difficulty: str,
    style_hint: str,
    en_questions: list[BilingualQuestion],
) -> list[BilingualQuestion]:
    """
    Generate Tamil versions of questions.
    Uses Tamil material + PYQ Tamil context to ensure natural Tamil phrasing.
    Each Tamil question is semantically equivalent to the matching English question.
    """
    llm = _llm()
    mat_ta = _retrieve_topic(db, topic_slug, f"{topic_slug} முக்கிய தகவல்கள்", TopicSourceKind.MATERIAL_TA, top_k=10)
    pyq_ta = _retrieve_topic(db, topic_slug, f"{topic_slug} வினா பாங்கு", TopicSourceKind.PYQ, top_k=8)

    ta_context = (
        "[தமிழ் பாட உள்ளடக்கம்]\n" + _build_context(mat_ta)
        + "\n\n[முந்தைய ஆண்டு வினாக்கள் - தமிழ் பாணி]\n" + _build_context(pyq_ta)
    )
    if not ta_context.strip():
        raise RuntimeError(
            f"No indexed Tamil content for topic '{topic_slug}'. "
            "Add Tamil PDFs to ta/ folder."
        )

    en_list_text = "\n".join(
        f"{i+1}. Q: {q.question_text}\n   Options: {q.options}\n   Answer: {q.answer}"
        for i, q in enumerate(en_questions)
    )

    parser = llm.with_structured_output(BilingualBatch)
    prompt = (
        f"You are an exam setter for {exam_type}. Convert the following {len(en_questions)} English MCQ questions "
        f"for subject '{subject}', topic '{topic_slug}' to Tamil. "
        f"Difficulty bucket: {difficulty}. "
        f"Difficulty behavior: {style_hint} "
        "Use the Tamil material context to ensure accurate, natural Tamil phrasing. "
        "Preserve the same meaning, answer, and exam style. "
        "Return exactly the same number of questions as input. "
        "Options must be in Tamil. Answer must be in Tamil matching one of the options. "
        "Return JSON only.\n\n"
        f"Tamil Context:\n{ta_context}\n\n"
        f"English Questions to convert:\n{en_list_text}"
    )
    out = parser.invoke(prompt)
    # Pad with fallbacks if LLM returns fewer
    result = list(out.questions[: len(en_questions)])
    while len(result) < len(en_questions):
        en_q = en_questions[len(result)]
        result.append(
            BilingualQuestion(
                question_text=f"[Tamil unavailable] {en_q.question_text}",
                options=en_q.options,
                answer=en_q.answer,
                explanation=en_q.explanation,
                difficulty=en_q.difficulty,
            )
        )
    return result


# ── Main job runner ──────────────────────────────────────────────

def run_topic_generation_job(db: Session, job_id: uuid.UUID) -> None:
    job = db.query(TopicGenerationJob).filter(TopicGenerationJob.id == job_id).first()
    if job is None:
        return
    try:
        set_info = db.query(TopicSetInfo).filter(TopicSetInfo.job_id == job.id).first()
        if set_info is None:
            raise RuntimeError("Missing topic set metadata for this generation job.")
        exam_type = set_info.exam_type
        subject = set_info.subject

        blueprint = _get_or_create_subject_blueprint(db, exam_type, subject)
        style_json = blueprint.style_json or {}
        difficulty_split = _difficulty_quota(
            total=job.num_questions,
            easy_pct=blueprint.easy_pct,
            moderate_pct=blueprint.moderate_pct,
            hard_pct=blueprint.hard_pct,
        )

        job.status = JobStatus.PROCESSING
        job.progress = 5
        job.started_at = datetime.utcnow()
        job.message = "Indexing topic documents"
        db.commit()

        ensure_topic_indexed(db, job.topic_slug)

        job.progress = 25
        job.message = "Generating English questions by difficulty"
        db.commit()

        en_questions: list[BilingualQuestion] = []
        for difficulty in ("easy", "moderate", "hard"):
            count = difficulty_split.get(difficulty, 0)
            if count <= 0:
                continue
            en_questions.extend(
                _gen_en_questions(
                    db=db,
                    exam_type=exam_type,
                    subject=subject,
                    topic_slug=job.topic_slug,
                    difficulty=difficulty,
                    count=count,
                    style_hint=str(style_json.get(difficulty, DEFAULT_STYLE_HINTS[difficulty])),
                )
            )

        job.progress = 55
        job.message = "Generating Tamil questions by difficulty"
        db.commit()

        ta_questions: list[BilingualQuestion] = []
        start_idx = 0
        for difficulty in ("easy", "moderate", "hard"):
            count = difficulty_split.get(difficulty, 0)
            if count <= 0:
                continue
            en_batch = en_questions[start_idx : start_idx + count]
            start_idx += count
            ta_questions.extend(
                _gen_ta_questions(
                    db=db,
                    exam_type=exam_type,
                    subject=subject,
                    topic_slug=job.topic_slug,
                    difficulty=difficulty,
                    style_hint=str(style_json.get(difficulty, DEFAULT_STYLE_HINTS[difficulty])),
                    en_questions=en_batch,
                )
            )

        job.progress = 80
        job.message = "Saving to database"
        db.commit()

        for idx, (en_q, ta_q) in enumerate(zip(en_questions, ta_questions), start=1):
            pattern = QuestionPattern(
                topic_slug=job.topic_slug,
                question_no=idx,
                difficulty=en_q.difficulty,
                job_id=job.id,
            )
            db.add(pattern)
            db.flush()

            db.add(
                TopicQuestionEn(
                    pattern_id=pattern.id,
                    topic_slug=job.topic_slug,
                    question_no=idx,
                    question_text=en_q.question_text,
                    options_json=en_q.options,
                    answer=en_q.answer,
                    explanation=en_q.explanation,
                    marks=1,
                )
            )
            db.add(
                TopicQuestionTa(
                    pattern_id=pattern.id,
                    topic_slug=job.topic_slug,
                    question_no=idx,
                    question_text=ta_q.question_text,
                    options_json=ta_q.options,
                    answer=ta_q.answer,
                    explanation=ta_q.explanation,
                    marks=1,
                )
            )

        db.commit()

        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.message = (
            f"Done. Set {set_info.set_no}: generated {len(en_questions)} EN + {len(ta_questions)} TA "
            f"with split {difficulty_split}."
        )
        job.finished_at = datetime.utcnow()
        db.commit()

    except Exception as exc:  # noqa: BLE001
        db.rollback()
        job = db.query(TopicGenerationJob).filter(TopicGenerationJob.id == job_id).first()
        if job is not None:
            job.status = JobStatus.FAILED
            job.error = str(exc)
            job.message = "Failed"
            job.finished_at = datetime.utcnow()
            db.commit()


# ── Serialization helpers ────────────────────────────────────────

def topic_job_to_dict(job: TopicGenerationJob) -> dict:
    return {
        "job_id": str(job.id),
        "set_no": None,
        "exam_type": None,
        "subject": None,
        "topic_slug": job.topic_slug,
        "num_questions": job.num_questions,
        "status": job.status.value,
        "progress": job.progress,
        "message": job.message,
        "error": job.error,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


def topic_questions_to_dict(
    patterns: list[QuestionPattern], lang: str, set_no: int | None = None, exam_type: str | None = None, subject: str | None = None
) -> list[dict]:
    out = []
    for p in sorted(patterns, key=lambda x: x.question_no):
        q = p.en_question if lang == "en" else p.ta_question
        if q is None:
            continue
        out.append(
            {
                "question_pattern_id": str(p.id),
                "set_no": set_no,
                "exam_type": exam_type,
                "subject": subject,
                "question_no": p.question_no,
                "difficulty": p.difficulty,
                "language": lang,
                "question_text": q.question_text,
                "options": list(q.options_json or []),
                "answer": q.answer,
                "explanation": q.explanation,
                "marks": q.marks,
            }
        )
    return out
