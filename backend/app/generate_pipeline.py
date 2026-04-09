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
    GenerationJob,
    JobStatus,
    QuestionItem,
    QuestionPaper,
    SourceChunk,
    SourceDocument,
    SourceKind,
)


SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}


class DistributionItem(BaseModel):
    subject: str
    percentage: int = Field(ge=1, le=100)


class DistributionOut(BaseModel):
    items: list[DistributionItem]


class GeneratedQuestion(BaseModel):
    subject: str
    topic: str = "general"
    difficulty: str = "medium"
    question_text: str
    options: list[str]
    answer: str
    explanation: str = ""


class GeneratedQuestionBatch(BaseModel):
    questions: list[GeneratedQuestion]


@dataclass
class DocInfo:
    path: Path
    kind: SourceKind
    exam_type: str
    subject: str


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _read_file_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join([(page.extract_text() or "") for page in reader.pages])
    return path.read_text(encoding="utf-8", errors="ignore")


def _chunks(text: str, size: int = 2200, overlap: int = 300) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    out: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + size)
        out.append(cleaned[start:end])
        if end >= len(cleaned):
            break
        start = end - overlap
    return out


def _scan_documents() -> list[DocInfo]:
    roots = [
        (Path(settings.rules_dir), SourceKind.RULES),
        (Path(settings.previous_year_dir), SourceKind.PREVIOUS_YEAR),
        (Path(settings.materials_dir), SourceKind.MATERIAL),
        (Path(settings.current_affairs_dir), SourceKind.CURRENT_AFFAIRS),
    ]
    out: list[DocInfo] = []
    for root, kind in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            rel = p.relative_to(root).parts
            exam_type = rel[0] if len(rel) > 0 else "GENERAL"
            subject = rel[1] if len(rel) > 1 else "general"
            out.append(DocInfo(path=p, kind=kind, exam_type=exam_type.upper(), subject=subject))
    return out


def _embedder() -> OpenAIEmbeddings:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is missing. Set it in backend/.env")
    return OpenAIEmbeddings(model=settings.embedding_model, api_key=settings.openai_api_key)


def ensure_documents_indexed(db: Session, exam_type: str) -> None:
    embed = _embedder()
    docs = [d for d in _scan_documents() if d.exam_type == exam_type.upper()]
    for d in docs:
        checksum = _sha256(d.path)
        row = db.query(SourceDocument).filter(SourceDocument.file_path == str(d.path)).first()
        changed = row is None or row.checksum != checksum
        if row is None:
            row = SourceDocument(
                exam_type=d.exam_type,
                subject=d.subject,
                kind=d.kind,
                file_path=str(d.path),
                checksum=checksum,
                is_indexed=False,
            )
            db.add(row)
            db.flush()
        elif changed:
            db.query(SourceChunk).filter(SourceChunk.document_id == row.id).delete()
            row.checksum = checksum
            row.is_indexed = False

        if row.is_indexed and not changed:
            continue

        text = _read_file_text(d.path)
        parts = _chunks(text)
        if not parts:
            row.is_indexed = True
            continue
        vectors = embed.embed_documents(parts)
        for i, (chunk_text, vec) in enumerate(zip(parts, vectors)):
            db.add(
                SourceChunk(
                    document_id=row.id,
                    exam_type=row.exam_type,
                    subject=row.subject,
                    kind=row.kind,
                    chunk_index=i,
                    content=chunk_text,
                    metadata_json={"file": str(d.path), "kind": row.kind.value},
                    embedding=vec,
                )
            )
        row.is_indexed = True
    db.commit()


def _retrieve(
    db: Session, exam_type: str, query: str, kind: SourceKind, subject: str | None = None, top_k: int = 8
) -> list[SourceChunk]:
    embed = _embedder()
    q = embed.embed_query(query)
    stmt = db.query(SourceChunk).filter(SourceChunk.exam_type == exam_type.upper(), SourceChunk.kind == kind)
    if subject:
        stmt = stmt.filter(SourceChunk.subject == subject)
    return stmt.order_by(SourceChunk.embedding.cosine_distance(q)).limit(top_k).all()


def _llm() -> ChatOpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is missing. Set it in backend/.env")
    return ChatOpenAI(model=settings.llm_model, api_key=settings.openai_api_key, temperature=0.2)


def _build_distribution(db: Session, exam_type: str, paper_size: int) -> dict[str, int]:
    llm = _llm()
    rules_chunks = _retrieve(
        db, exam_type, f"Create subject-wise question percentages for {exam_type} exam.", SourceKind.RULES, top_k=14
    )
    rules_text = "\n\n".join([c.content[:1500] for c in rules_chunks])
    if not rules_text:
        raise RuntimeError(f"No rules documents found for {exam_type}. Add PDFs under {settings.rules_dir}/{exam_type}/")

    structured = llm.with_structured_output(DistributionOut)
    result = structured.invoke(
        (
            "Extract subject percentage distribution from exam rules. "
            "Return only realistic subjects with integer percentages that sum to 100."
            "\nRules:\n"
            f"{rules_text}"
        )
    )
    items = result.items
    if not items:
        raise RuntimeError("Could not extract subject distribution from rules.")

    raw = {i.subject.strip(): max(1, int(i.percentage)) for i in items}
    total = sum(raw.values())
    scaled = {k: max(1, int(round(v * 100 / total))) for k, v in raw.items()}
    # normalize to exactly 100
    diff = 100 - sum(scaled.values())
    keys = list(scaled.keys())
    idx = 0
    while diff != 0 and keys:
        k = keys[idx % len(keys)]
        if diff > 0:
            scaled[k] += 1
            diff -= 1
        elif scaled[k] > 1:
            scaled[k] -= 1
            diff += 1
        idx += 1

    quotas = {k: max(1, math.floor(v * paper_size / 100)) for k, v in scaled.items()}
    q_diff = paper_size - sum(quotas.values())
    q_keys = list(quotas.keys())
    idx = 0
    while q_diff != 0 and q_keys:
        k = q_keys[idx % len(q_keys)]
        if q_diff > 0:
            quotas[k] += 1
            q_diff -= 1
        elif quotas[k] > 1:
            quotas[k] -= 1
            q_diff += 1
        idx += 1
    return quotas


def _generate_for_subject(db: Session, exam_type: str, subject: str, count: int) -> list[GeneratedQuestion]:
    llm = _llm()
    pattern_chunks = _retrieve(
        db, exam_type, f"{subject} previous year question style and pattern", SourceKind.PREVIOUS_YEAR, top_k=10
    )
    material_chunks = _retrieve(
        db, exam_type, f"{subject} core concepts for exam preparation", SourceKind.MATERIAL, top_k=12
    )
    current_chunks = _retrieve(
        db, exam_type, f"{subject} recent current affairs and updates", SourceKind.CURRENT_AFFAIRS, top_k=6
    )
    context = "\n\n".join(
        [f"[PATTERN] {c.content[:900]}" for c in pattern_chunks]
        + [f"[CONTENT] {c.content[:900]}" for c in material_chunks]
        + [f"[CURRENT] {c.content[:700]}" for c in current_chunks]
    )
    if not context:
        raise RuntimeError(
            f"No source docs for subject '{subject}'. Add files under previous_year/materials/current_affairs."
        )
    parser = llm.with_structured_output(GeneratedQuestionBatch)
    prompt = (
        f"Generate {count} fresh exam questions for {exam_type} - subject {subject}. "
        "Return valid JSON only using schema. "
        "Constraints: mostly MCQ with 4 options; include concise answer and explanation. "
        "Avoid copying exact previous-year questions. Keep exam style and difficulty balance."
        f"\nContext:\n{context}"
    )
    out = parser.invoke(prompt)
    return out.questions[:count]


def _next_paper_number(db: Session, exam_type: str) -> int:
    value = db.query(func.max(QuestionPaper.paper_number)).filter(QuestionPaper.exam_type == exam_type.upper()).scalar()
    return (value or 0) + 1


def run_generation_job(db: Session, job_id: uuid.UUID) -> None:
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
    if job is None:
        return
    try:
        job.status = JobStatus.PROCESSING
        job.progress = 3
        job.started_at = datetime.utcnow()
        job.message = "Indexing source documents"
        db.commit()

        ensure_documents_indexed(db, job.exam_type)

        job.progress = 20
        job.message = "Extracting rule distribution"
        db.commit()
        quotas = _build_distribution(db, job.exam_type, job.paper_size)

        paper = QuestionPaper(
            exam_type=job.exam_type.upper(),
            paper_number=_next_paper_number(db, job.exam_type),
            paper_size=job.paper_size,
            rules_version=job.rules_version,
            meta_json={"distribution": quotas},
        )
        db.add(paper)
        db.flush()

        generated: list[GeneratedQuestion] = []
        processed = 0
        total = max(1, len(quotas))
        for subject, count in quotas.items():
            qs = _generate_for_subject(db, job.exam_type, subject, count)
            generated.extend(qs)
            processed += 1
            job.progress = 20 + int((processed / total) * 70)
            job.message = f"Generated {subject}"
            db.commit()

        # dedupe by normalized question text
        seen: set[str] = set()
        unique: list[GeneratedQuestion] = []
        for q in generated:
            key = re.sub(r"\s+", " ", q.question_text).strip().lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(q)

        unique = unique[: job.paper_size]
        for idx, q in enumerate(unique, start=1):
            db.add(
                QuestionItem(
                    paper_id=paper.id,
                    question_no=idx,
                    subject=q.subject,
                    topic=q.topic,
                    question_type="mcq",
                    difficulty=q.difficulty,
                    question_text=q.question_text,
                    options_json=q.options,
                    answer=q.answer,
                    explanation=q.explanation,
                    marks=1,
                    meta_json={},
                )
            )
        db.commit()

        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.message = "Completed"
        job.finished_at = datetime.utcnow()
        job.paper_id = paper.id
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
        if job is not None:
            job.status = JobStatus.FAILED
            job.error = str(exc)
            job.message = "Failed"
            job.finished_at = datetime.utcnow()
            db.commit()


def to_job_status(job: GenerationJob) -> dict:
    return {
        "job_id": str(job.id),
        "status": job.status.value,
        "progress": job.progress,
        "exam_type": job.exam_type,
        "paper_size": job.paper_size,
        "paper_id": str(job.paper_id) if job.paper_id else None,
        "message": job.message,
        "error": job.error,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


def to_paper_out(paper: QuestionPaper) -> dict:
    return {
        "paper_id": str(paper.id),
        "exam_type": paper.exam_type,
        "paper_number": paper.paper_number,
        "paper_size": paper.paper_size,
        "rules_version": paper.rules_version,
        "created_at": paper.created_at,
        "questions": [
            {
                "question_no": q.question_no,
                "subject": q.subject,
                "topic": q.topic,
                "question_type": q.question_type,
                "difficulty": q.difficulty,
                "question_text": q.question_text,
                "options": list(q.options_json or []),
                "answer": q.answer,
                "explanation": q.explanation,
                "marks": q.marks,
            }
            for q in sorted(paper.questions, key=lambda x: x.question_no)
        ],
    }
