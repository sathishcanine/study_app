import secrets
import uuid
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.responses import Response
from sqlalchemy import func, or_, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.auth_utils import create_access_token, decode_token, get_user_by_email, hash_password, verify_password
from app.config import settings
from app.database import Base, SessionLocal, engine, get_db
from app.pyq_schema_migration import ensure_pyq_question_schema
from app.generate_pipeline import run_generation_job, to_job_status, to_paper_out
from app.google_verify import verify_google_id_token
from app.models import (
    GenerationJob,
    JobStatus,
    PyqDocument,
    PyqIngestStatus,
    PyqQuestion,
    PyqSubject,
    QuestionPaper,
    QuestionPattern,
    TopicGenerationJob,
    TopicSetAttempt,
    TopicSetInfo,
    User,
)
from app.schemas import (
    CompletedSetListOut,
    CompletedSetOut,
    GeneratePaperIn,
    GenerateTopicQuestionsIn,
    GoogleAuthIn,
    JobQueuedOut,
    JobStatusOut,
    LeaderboardEntry,
    PaperOut,
    PyqFiltersOut,
    PyqImportJsonIn,
    PyqPasteTextIn,
    PyqQuestionOut,
    PyqQuestionPageOut,
    PyqSubjectListOut,
    PyqSubjectOut,
    QuizResultIn,
    SetLeaderboardEntry,
    SetLeaderboardOut,
    TokenResponse,
    TopicSetAttemptIn,
    TopicSetAttemptOut,
    TopicJobQueuedOut,
    TopicJobStatusOut,
    SubjectSetListOut,
    TopicSetListOut,
    TopicSetOut,
    TopicQuestionsOut,
    UserLogin,
    UserRegister,
)
from app.pyq_pipeline import (
    import_pyq_manual_json,
    ingest_pasted_text_with_openai,
    ingest_previous_year_documents,
    ingest_subject_with_openai,
    sync_pyq_catalog_from_files,
)
from app.topic_pipeline import (
    is_valid_subject_for_exam,
    run_topic_generation_job,
    topic_job_to_dict,
    topic_questions_to_dict,
)

security = HTTPBearer(auto_error=False)
logger = logging.getLogger("uvicorn.error")


def user_profile_dict(user: User) -> dict:
    return {
        "email": user.email,
        "username": user.username,
        "score": user.score,
        "correctAnswer": user.correct_answer,
        "quizTaken": user.quiz_taken,
        "totalQuestions": user.total_questions,
        "history": user.history if user.history is not None else [],
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    except OperationalError as exc:
        err = str(exc).lower()
        if "vector.control" in err or "create extension if not exists vector" in err:
            raise RuntimeError(
                "pgvector extension is not installed in your Postgres instance.\n"
                "Install and enable it, then restart the API.\n"
                "For Homebrew + PostgreSQL 14:\n"
                "  brew install pgvector\n"
                "  psql -d <your_db_name> -c 'CREATE EXTENSION IF NOT EXISTS vector;'"
            ) from exc
        raise
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        ensure_pyq_question_schema(conn)
    # One-time PYQ sync + ingest per server start (not request-time).
    s = SessionLocal()
    try:
        logger.info("PYQ startup catalog sync started")
        sync_summary = sync_pyq_catalog_from_files(s)
        logger.info("PYQ startup catalog sync done: %s", sync_summary)
        if settings.pyq_run_startup_ingest:
            startup_slug = (settings.pyq_startup_subject_slug or "").strip().lower() or None
            logger.info("PYQ startup ingest started (filter=%s)", startup_slug or "all")
            ingest_summary = ingest_previous_year_documents(s, subject_slug_filter=startup_slug)
            logger.info("PYQ startup ingest done: %s", ingest_summary)
        else:
            logger.info(
                "PYQ startup ingest skipped (pyq_run_startup_ingest=false). "
                "Use POST /admin/pyq/ingest or POST /admin/pyq/ingest-openai when needed."
            )
    finally:
        s.close()
    yield


app = FastAPI(title="Study App API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_current_user_email(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> str:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    email = decode_token(creds.credentials)
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return email


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    if not x_admin_key or x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin key.")


def exam_type_match(column, exam_type_raw: str):
    """
    Match exact exam type, and for family keys like TNPSC include TNPSC_* variants.
    Example: TNPSC matches TNPSC and TNPSC_GROUP1.
    """
    exam_type_key = exam_type_raw.upper().strip()
    if "_" in exam_type_key:
        return column == exam_type_key
    return or_(column == exam_type_key, column.like(f"{exam_type_key}_%"))


def _build_set_ranks(attempts: list[TopicSetAttempt]) -> tuple[dict[str, int], int]:
    """
    Dense rank by score desc, then attempted_at asc.
    Returns (email -> rank, total_takers).
    """
    ordered = sorted(attempts, key=lambda a: (-a.score, a.attempted_at))
    ranks: dict[str, int] = {}
    rank = 0
    prev_score: int | None = None
    for i, a in enumerate(ordered):
        if prev_score is None or a.score != prev_score:
            rank = i + 1
            prev_score = a.score
        ranks[a.user_email] = rank
    return ranks, len(ordered)


@app.post("/auth/register", response_model=TokenResponse)
def register(body: UserRegister, db: Session = Depends(get_db)):
    if get_user_by_email(db, body.email):
        raise HTTPException(status_code=400, detail="An account already exists for that email.")
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        username=body.username,
        score=body.score,
        correct_answer=0,
        quiz_taken=0,
        total_questions=0,
        history=[],
    )
    db.add(user)
    db.commit()
    token = create_access_token(body.email)
    return TokenResponse(access_token=token)


@app.post("/auth/login", response_model=TokenResponse)
def login(body: UserLogin, db: Session = Depends(get_db)):
    user = get_user_by_email(db, body.email)
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return TokenResponse(access_token=create_access_token(user.email))


@app.post("/auth/google", response_model=TokenResponse)
def auth_google(body: GoogleAuthIn, db: Session = Depends(get_db)):
    try:
        claims = verify_google_id_token(body.id_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    email = claims.get("email")
    if not email or not isinstance(email, str):
        raise HTTPException(status_code=400, detail="Google account has no email.")
    if not claims.get("email_verified", False):
        raise HTTPException(status_code=400, detail="Google email is not verified.")
    name_raw = claims.get("name")
    name = (name_raw if isinstance(name_raw, str) else None) or email.split("@", 1)[0]
    name = name[:255]
    user = get_user_by_email(db, email)
    if not user:
        user = User(
            email=email,
            hashed_password=hash_password(secrets.token_urlsafe(48)),
            username=name,
            score=0,
            correct_answer=0,
            quiz_taken=0,
            total_questions=0,
            history=[],
        )
        db.add(user)
        db.commit()
    return TokenResponse(access_token=create_access_token(email), email=email)


@app.get("/users/me")
def read_me(email: str = Depends(get_current_user_email), db: Session = Depends(get_db)):
    user = get_user_by_email(db, email)
    assert user is not None
    return user_profile_dict(user)


@app.post("/users/me/quiz-result")
def record_quiz_result(
    body: QuizResultIn,
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
):
    user = get_user_by_email(db, email)
    assert user is not None
    # Keep only aggregate counters in users table; per-test details belong to dedicated attempt tables.
    user.score = user.score + body.score
    user.total_questions = user.total_questions + body.question_numbers
    user.quiz_taken = user.quiz_taken + 1
    user.correct_answer = user.correct_answer + body.correct_answers
    user.history = []
    db.commit()
    return user_profile_dict(user)


@app.get("/leaderboard", response_model=list[LeaderboardEntry])
def leaderboard(db: Session = Depends(get_db)):
    rows = db.query(User).order_by(User.score.desc()).all()
    return [LeaderboardEntry(username=u.username, score=u.score) for u in rows]


@app.get("/")
def root():
    """Human-friendly landing when opening the server URL in a browser."""
    return {
        "service": app.title,
        "docs": "/docs",
        "openapi": "/openapi.json",
        "health": "/health",
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/admin/pyq/ingest", dependencies=[Depends(require_admin)])
def ingest_pyq(subject_slug: str | None = None, db: Session = Depends(get_db)):
    slug = (subject_slug or "").strip().lower() or None
    return ingest_previous_year_documents(db, subject_slug_filter=slug)


@app.post("/admin/pyq/ingest-openai", dependencies=[Depends(require_admin)])
def ingest_pyq_openai(
    subject_slug: str,
    max_questions: int = 450,
    db: Session = Depends(get_db),
):
    return ingest_subject_with_openai(db, subject_slug=subject_slug, max_questions=max_questions)


@app.post("/admin/pyq/reingest-openai", dependencies=[Depends(require_admin)])
def reingest_pyq_openai(
    subject_slug: str,
    max_questions: int = 450,
    db: Session = Depends(get_db),
):
    """
    Clears all stored questions for the subject, resets document ingest flags, then runs OpenAI PDF ingest.
    Same end state as `scripts/clear_and_ingest_chemistry_pyq.py` for the given slug.
    """
    key = (subject_slug or "").strip().lower()
    if not key:
        raise HTTPException(status_code=400, detail="subject_slug is required")
    subject = db.query(PyqSubject).filter(PyqSubject.subject_slug == key).first()
    if subject is None:
        raise HTTPException(status_code=404, detail="PYQ subject not found")
    deleted = db.query(PyqQuestion).filter(PyqQuestion.subject_id == subject.id).delete(synchronize_session=False)
    for doc in db.query(PyqDocument).filter(PyqDocument.subject_id == subject.id).all():
        doc.total_questions = 0
        doc.status = PyqIngestStatus.PENDING
    db.commit()
    summary = ingest_subject_with_openai(db, subject_slug=key, max_questions=max_questions)
    summary["prior_questions_deleted"] = deleted
    return summary


@app.post("/admin/pyq/import-json", dependencies=[Depends(require_admin)])
def pyq_import_json(body: PyqImportJsonIn, db: Session = Depends(get_db)):
    """Insert questions from JSON (e.g. typed from ChatGPT). Does not call OpenAI."""
    return import_pyq_manual_json(
        db,
        subject_slug=body.subject_slug,
        rows=body.questions,
        replace_subject_questions=body.replace_subject_questions,
    )


@app.post("/admin/pyq/ingest-paste", dependencies=[Depends(require_admin)])
def pyq_ingest_paste(body: PyqPasteTextIn, db: Session = Depends(get_db)):
    """Parse pasted question text with OpenAI structured output, then insert rows."""
    return ingest_pasted_text_with_openai(
        db,
        subject_slug=body.subject_slug,
        raw_text=body.raw_text,
        append=body.append,
        max_questions=body.max_questions,
    )


@app.get("/pyq/subjects", response_model=PyqSubjectListOut)
def get_pyq_subjects(
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user_email),
):
    sync_pyq_catalog_from_files(db)
    subjects = db.query(PyqSubject).filter(PyqSubject.is_active.is_(True)).order_by(PyqSubject.subject_name.asc()).all()
    items: list[PyqSubjectOut] = []
    for s in subjects:
        total_questions = (
            db.query(func.count(PyqQuestion.id))
            .filter(PyqQuestion.subject_id == s.id)
            .scalar()
            or 0
        )
        total_documents = (
            db.query(func.count(PyqDocument.id))
            .filter(PyqDocument.subject_id == s.id)
            .scalar()
            or 0
        )
        items.append(
            PyqSubjectOut(
                subject_slug=s.subject_slug,
                subject_name=s.subject_name,
                total_questions=int(total_questions),
                total_documents=int(total_documents),
            )
        )
    return PyqSubjectListOut(total_subjects=len(items), subjects=items)


@app.get("/pyq/subjects/{subject_slug}/filters", response_model=PyqFiltersOut)
def get_pyq_filters(
    subject_slug: str,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user_email),
):
    subject = db.query(PyqSubject).filter(PyqSubject.subject_slug == subject_slug).first()
    if not subject:
        raise HTTPException(status_code=404, detail="PYQ subject not found")

    years = sorted(
        {int(y) for (y,) in db.query(PyqQuestion.year).filter(PyqQuestion.subject_id == subject.id).all() if y is not None},
        reverse=True,
    )
    topic_vals = sorted(
        {
            st.strip()
            for (st,) in db.query(PyqQuestion.topic).filter(PyqQuestion.subject_id == subject.id).all()
            if st and st.strip()
        }
    )
    return PyqFiltersOut(subject_slug=subject_slug, years=years, topics=topic_vals, subtopics=topic_vals)


@app.get("/pyq/subjects/{subject_slug}/questions", response_model=PyqQuestionPageOut)
def get_pyq_questions(
    subject_slug: str,
    year: int | None = None,
    subtopic: str | None = None,
    topic: str | None = None,
    page: int = 1,
    limit: int = 20,
    source: str | None = None,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user_email),
):
    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100")

    subject = db.query(PyqSubject).filter(PyqSubject.subject_slug == subject_slug).first()
    if not subject:
        raise HTTPException(status_code=404, detail="PYQ subject not found")

    meta_src = func.coalesce(PyqQuestion.raw_meta_json["source"].astext, "")
    openai_any = (
        db.query(func.count(PyqQuestion.id))
        .filter(PyqQuestion.subject_id == subject.id, meta_src.like("%openai%"))
        .scalar()
        or 0
    )
    src_mode = (source or "").strip().lower()
    if not src_mode or src_mode == "auto":
        src_mode = "openai" if int(openai_any) > 0 else "all"
    if src_mode not in ("all", "openai", "legacy"):
        raise HTTPException(
            status_code=400,
            detail="source must be one of: all, openai, legacy, auto (default auto)",
        )

    q = db.query(PyqQuestion).filter(PyqQuestion.subject_id == subject.id)
    if year is not None:
        q = q.filter(PyqQuestion.year == year)
    topic_filter = (topic or subtopic or "").strip()
    if topic_filter:
        q = q.filter(PyqQuestion.topic == topic_filter)
    if src_mode == "openai":
        q = q.filter(meta_src.like("%openai%"))
    elif src_mode == "legacy":
        q = q.filter(~meta_src.like("%openai%"))

    total = q.count()
    rows = (
        q.order_by(PyqQuestion.year.desc().nullslast(), PyqQuestion.question_no.asc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    questions: list[PyqQuestionOut] = []
    for row in rows:
        meta = row.raw_meta_json if isinstance(row.raw_meta_json, dict) else {}
        legacy_full = (meta.get("answer_full") or meta.get("correct_answer") or "").strip()
        ca = (row.correct_answer or "").strip()
        answer_display = ca or legacy_full or (row.answer_key or "").strip()
        oen = list(row.options_en or [])
        ota = list(row.options_ta or [])
        qen = (row.question_en or "").strip()
        qta = (row.question_ta or "").strip()
        expl = (row.explanation or "").strip() or (row.explanation_bilingual or "").strip()
        exv = (row.exam or "").strip() or None
        top = (row.topic or "").strip() or None
        questions.append(
            PyqQuestionOut(
                id=str(row.id),
                question_no=row.question_no,
                question_en=qen,
                question_ta=qta,
                options_en=oen,
                options_ta=ota,
                correct_answer=ca or legacy_full,
                explanation=expl,
                exam=exv,
                year=row.year,
                topic=top,
                question_text_bilingual=row.question_text_bilingual,
                options=list(row.options_json or []),
                answer_key=row.answer_key,
                answer_display=answer_display,
                explanation_bilingual=row.explanation_bilingual,
                subtopic=top,
                exam_name=exv,
                content_source=meta.get("source") if isinstance(meta.get("source"), str) else None,
            )
        )
    return PyqQuestionPageOut(
        subject_slug=subject_slug,
        total=total,
        page=page,
        limit=limit,
        questions=questions,
    )


@app.post("/generate-paper", response_model=JobQueuedOut, dependencies=[Depends(require_admin)])
def generate_paper(
    body: GeneratePaperIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    exam_type = body.exam_type.upper().strip()
    today = datetime.now(timezone.utc).date().isoformat()

    running = (
        db.query(GenerationJob)
        .filter(
            GenerationJob.exam_type == exam_type,
            GenerationJob.status.in_([JobStatus.QUEUED, JobStatus.PROCESSING]),
        )
        .first()
    )
    if running:
        raise HTTPException(status_code=409, detail="A generation job is already running for this exam type.")

    if not body.force_new:
        same_day = (
            db.query(GenerationJob)
            .filter(
                GenerationJob.exam_type == exam_type,
                GenerationJob.paper_date == today,
                GenerationJob.status == JobStatus.COMPLETED,
            )
            .first()
        )
        if same_day:
            return JobQueuedOut(
                job_id=str(same_day.id),
                status=same_day.status.value,
                message="Paper already generated today. Use force_new=true to generate again.",
            )

    job = GenerationJob(
        exam_type=exam_type,
        paper_size=body.paper_size,
        rules_version=body.rules_version,
        paper_date=today,
        status=JobStatus.QUEUED,
        progress=0,
        message="Queued",
        current_affairs_from=body.current_affairs_date_from,
        current_affairs_to=body.current_affairs_date_to,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    def _runner(job_id: uuid.UUID) -> None:
        s = SessionLocal()
        try:
            run_generation_job(s, job_id)
        finally:
            s.close()

    background_tasks.add_task(_runner, job.id)
    return JobQueuedOut(job_id=str(job.id), status=job.status.value, message="Paper generation started")


@app.get("/generate-paper/{job_id}", response_model=JobStatusOut, dependencies=[Depends(require_admin)])
def get_generate_job(job_id: str, db: Session = Depends(get_db)):
    try:
        uid = uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid job_id") from exc

    job = db.query(GenerationJob).filter(GenerationJob.id == uid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusOut(**to_job_status(job))


@app.get("/papers/{paper_id}", response_model=PaperOut, dependencies=[Depends(require_admin)])
def get_paper(paper_id: str, db: Session = Depends(get_db)):
    try:
        uid = uuid.UUID(paper_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid paper_id") from exc
    paper = db.query(QuestionPaper).filter(QuestionPaper.id == uid).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return PaperOut(**to_paper_out(paper))


# ── Topic-wise bilingual question generation ────────────────────

@app.post("/generate-topic-questions", response_model=TopicJobQueuedOut, dependencies=[Depends(require_admin)])
def generate_topic_questions(
    body: GenerateTopicQuestionsIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Admin-only. Generates N questions (English + Tamil) for a specific topic.

    Place PDFs under:
      backend/data/topics/<topic_slug>/en/   ← English material
      backend/data/topics/<topic_slug>/ta/   ← Tamil material
      backend/data/topics/<topic_slug>/pyq/  ← PYQ (bilingual)

    Each question gets a shared `question_pattern_id` linking EN and TA versions.
    """
    exam_type = body.exam_type.upper().strip()
    subject = body.subject.strip().lower().replace(" ", "_")
    if not is_valid_subject_for_exam(exam_type, subject):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid subject for exam_type. For TNPSC use one of: "
                "general_science, current_affairs, geography, history_and_culture_of_india, "
                "indian_polity, indian_economy, indian_national_movement, "
                "aptitude_and_mental_ability, tamil_language, english_language."
            ),
        )

    running = (
        db.query(TopicGenerationJob)
        .join(TopicSetInfo, TopicSetInfo.job_id == TopicGenerationJob.id)
        .filter(
            TopicGenerationJob.status.in_([JobStatus.QUEUED, JobStatus.PROCESSING]),
            TopicSetInfo.exam_type == exam_type,
            TopicSetInfo.subject == subject,
            TopicSetInfo.topic_slug == body.topic_slug,
        )
        .first()
    )
    if running:
        raise HTTPException(
            status_code=409, detail="A generation job is already running for this topic."
        )

    job = TopicGenerationJob(
        topic_slug=body.topic_slug,
        num_questions=body.num_questions,
        status=JobStatus.QUEUED,
        progress=0,
        message="Queued",
    )
    db.add(job)
    db.flush()

    set_no_max = (
        db.query(func.max(TopicSetInfo.set_no))
        .filter(
            TopicSetInfo.exam_type == exam_type,
            TopicSetInfo.subject == subject,
            TopicSetInfo.topic_slug == body.topic_slug,
        )
        .scalar()
    )
    next_set_no = int(set_no_max or 0) + 1
    db.add(
        TopicSetInfo(
            job_id=job.id,
            exam_type=exam_type,
            subject=subject,
            topic_slug=body.topic_slug,
            set_no=next_set_no,
        )
    )
    db.commit()
    db.refresh(job)

    def _runner(job_id: uuid.UUID) -> None:
        s = SessionLocal()
        try:
            run_topic_generation_job(s, job_id)
        finally:
            s.close()

    background_tasks.add_task(_runner, job.id)
    return TopicJobQueuedOut(
        job_id=str(job.id),
        set_no=next_set_no,
        exam_type=exam_type,
        subject=subject,
        topic_slug=job.topic_slug,
        status=job.status.value,
        message="Topic question generation started",
    )


@app.get(
    "/generate-topic-questions/{job_id}",
    response_model=TopicJobStatusOut,
    dependencies=[Depends(require_admin)],
)
def get_topic_job(job_id: str, db: Session = Depends(get_db)):
    """Poll job status for topic question generation."""
    try:
        uid = uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid job_id") from exc
    job = db.query(TopicGenerationJob).filter(TopicGenerationJob.id == uid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    payload = topic_job_to_dict(job)
    info = db.query(TopicSetInfo).filter(TopicSetInfo.job_id == job.id).first()
    if info:
        payload["set_no"] = info.set_no
        payload["exam_type"] = info.exam_type
        payload["subject"] = info.subject
    return TopicJobStatusOut(**payload)


@app.get("/topics/{topic_slug}/questions", response_model=TopicQuestionsOut)
def get_topic_questions(
    topic_slug: str,
    exam_type: str,
    subject: str,
    set_no: int,
    lang: str = "en",
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user_email),
):
    """
    Fetch generated questions for a topic in English (`lang=en`) or Tamil (`lang=ta`).
    Authenticated users only. `question_pattern_id` links each EN question to its TA counterpart.
    """
    if lang not in ("en", "ta"):
        raise HTTPException(status_code=400, detail="lang must be 'en' or 'ta'")

    subject_key = subject.strip().lower().replace(" ", "_")
    set_info = (
        db.query(TopicSetInfo)
        .filter(
            TopicSetInfo.topic_slug == topic_slug,
            exam_type_match(TopicSetInfo.exam_type, exam_type),
            TopicSetInfo.subject == subject_key,
            TopicSetInfo.set_no == set_no,
        )
        .first()
    )
    if not set_info:
        raise HTTPException(status_code=404, detail="Set not found for given topic/exam/subject/set_no")

    patterns = (
        db.query(QuestionPattern)
        .filter(QuestionPattern.topic_slug == topic_slug, QuestionPattern.job_id == set_info.job_id)
        .order_by(QuestionPattern.question_no)
        .all()
    )
    if not patterns:
        raise HTTPException(
            status_code=404,
            detail=f"No questions found for topic '{topic_slug}'. Generate them first.",
        )

    questions = topic_questions_to_dict(
        patterns,
        lang,
        set_no=set_info.set_no,
        exam_type=set_info.exam_type,
        subject=set_info.subject,
    )
    return TopicQuestionsOut(
        set_no=set_info.set_no,
        exam_type=set_info.exam_type,
        subject=set_info.subject,
        topic_slug=topic_slug,
        language=lang,
        total=len(questions),
        questions=questions,
    )


@app.get("/topics/{topic_slug}/sets", response_model=TopicSetListOut)
def get_topic_sets(
    topic_slug: str,
    exam_type: str,
    subject: str,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user_email),
):
    """List all generated sets for a topic/exam/subject."""
    exam_type_key = exam_type.upper().strip()
    subject_key = subject.strip().lower().replace(" ", "_")

    rows = (
        db.query(TopicSetInfo, TopicGenerationJob)
        .join(TopicGenerationJob, TopicGenerationJob.id == TopicSetInfo.job_id)
        .filter(
            TopicSetInfo.topic_slug == topic_slug,
            exam_type_match(TopicSetInfo.exam_type, exam_type),
            TopicSetInfo.subject == subject_key,
        )
        .order_by(TopicSetInfo.set_no.desc())
        .all()
    )
    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No sets found for given topic/exam/subject.",
        )

    me_email = _
    items: list[TopicSetOut] = []
    for info, job in rows:
        attempts = (
            db.query(TopicSetAttempt)
            .filter(TopicSetAttempt.set_info_id == info.id)
            .all()
        )
        rank_map, takers = _build_set_ranks(attempts)
        my_attempt = next((a for a in attempts if a.user_email == me_email), None)
        items.append(
            TopicSetOut(
                id=str(info.id),
                set_no=info.set_no,
                exam_type=info.exam_type,
                subject=info.subject,
                topic_slug=info.topic_slug,
                job_id=str(job.id),
                job_status=job.status.value,
                num_questions=job.num_questions,
                created_at=info.created_at,
                total_takers=takers,
                attempted_by_me=my_attempt is not None,
                my_rank=rank_map.get(me_email),
                my_score=my_attempt.score if my_attempt else None,
            )
        )
    return TopicSetListOut(
        exam_type=exam_type_key,
        subject=subject_key,
        topic_slug=topic_slug,
        total_sets=len(items),
        sets=items,
    )


@app.get("/subjects/{subject}/sets", response_model=SubjectSetListOut)
def get_subject_sets(
    subject: str,
    exam_type: str,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user_email),
):
    """List all generated sets for a subject across topic slugs."""
    exam_type_key = exam_type.upper().strip()
    subject_key = subject.strip().lower().replace(" ", "_")

    rows = (
        db.query(TopicSetInfo, TopicGenerationJob)
        .join(TopicGenerationJob, TopicGenerationJob.id == TopicSetInfo.job_id)
        .filter(
            exam_type_match(TopicSetInfo.exam_type, exam_type),
            TopicSetInfo.subject == subject_key,
        )
        .order_by(TopicSetInfo.created_at.desc(), TopicSetInfo.set_no.desc())
        .all()
    )
    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No sets found for given exam/subject.",
        )

    me_email = _
    items: list[TopicSetOut] = []
    for info, job in rows:
        attempts = (
            db.query(TopicSetAttempt)
            .filter(TopicSetAttempt.set_info_id == info.id)
            .all()
        )
        rank_map, takers = _build_set_ranks(attempts)
        my_attempt = next((a for a in attempts if a.user_email == me_email), None)
        items.append(
            TopicSetOut(
                id=str(info.id),
                set_no=info.set_no,
                exam_type=info.exam_type,
                subject=info.subject,
                topic_slug=info.topic_slug,
                job_id=str(job.id),
                job_status=job.status.value,
                num_questions=job.num_questions,
                created_at=info.created_at,
                total_takers=takers,
                attempted_by_me=my_attempt is not None,
                my_rank=rank_map.get(me_email),
                my_score=my_attempt.score if my_attempt else None,
            )
        )
    return SubjectSetListOut(
        exam_type=exam_type_key,
        subject=subject_key,
        total_sets=len(items),
        sets=items,
    )


@app.post("/topic-sets/{set_id}/attempts", response_model=TopicSetAttemptOut)
def submit_topic_set_attempt(
    set_id: str,
    body: TopicSetAttemptIn,
    db: Session = Depends(get_db),
    email: str = Depends(get_current_user_email),
):
    """Submit one attempt for a set. A user can attempt a set only once."""
    try:
        sid = uuid.UUID(set_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid set_id") from exc

    set_info = db.query(TopicSetInfo).filter(TopicSetInfo.id == sid).first()
    if not set_info:
        raise HTTPException(status_code=404, detail="Set not found")

    existing = (
        db.query(TopicSetAttempt)
        .filter(
            TopicSetAttempt.set_info_id == sid,
            TopicSetAttempt.user_email == email,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="You have already attempted this set.")

    attempt = TopicSetAttempt(
        set_info_id=sid,
        user_email=email,
        score=body.score,
        correct_answers=body.correct_answers,
        total_questions=body.total_questions,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    attempts = db.query(TopicSetAttempt).filter(TopicSetAttempt.set_info_id == sid).all()
    rank_map, takers = _build_set_ranks(attempts)
    return TopicSetAttemptOut(
        set_id=set_id,
        user_email=email,
        score=attempt.score,
        correct_answers=attempt.correct_answers,
        total_questions=attempt.total_questions,
        rank=rank_map[email],
        total_takers=takers,
        attempted_at=attempt.attempted_at,
    )


@app.get("/topic-sets/{set_id}/leaderboard", response_model=SetLeaderboardOut)
def get_topic_set_leaderboard(
    set_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user_email),
):
    """Leaderboard for a specific set."""
    try:
        sid = uuid.UUID(set_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid set_id") from exc

    set_info = db.query(TopicSetInfo).filter(TopicSetInfo.id == sid).first()
    if not set_info:
        raise HTTPException(status_code=404, detail="Set not found")

    attempts = db.query(TopicSetAttempt).filter(TopicSetAttempt.set_info_id == sid).all()
    rank_map, takers = _build_set_ranks(attempts)

    users = {u.email: u.username for u in db.query(User).all()}
    ordered = sorted(attempts, key=lambda a: (-a.score, a.attempted_at))
    entries = [
        SetLeaderboardEntry(
            rank=rank_map[a.user_email],
            email=a.user_email,
            username=users.get(a.user_email, a.user_email.split("@", 1)[0]),
            score=a.score,
            correct_answers=a.correct_answers,
            total_questions=a.total_questions,
            attempted_at=a.attempted_at,
        )
        for a in ordered
    ]

    return SetLeaderboardOut(
        set_id=set_id,
        exam_type=set_info.exam_type,
        subject=set_info.subject,
        topic_slug=set_info.topic_slug,
        set_no=set_info.set_no,
        total_takers=takers,
        entries=entries,
    )


@app.get("/users/me/completed-topic-sets", response_model=CompletedSetListOut)
def get_my_completed_topic_sets(
    exam_type: str,
    subject: str | None = None,
    db: Session = Depends(get_db),
    email: str = Depends(get_current_user_email),
):
    """
    Completed sets for current user (for frontend Completed tab),
    including current rank and total takers per set.
    """
    attempts_q = db.query(TopicSetAttempt).filter(TopicSetAttempt.user_email == email)
    if subject:
        subject_key = subject.strip().lower().replace(" ", "_")
        attempts_q = attempts_q.join(TopicSetInfo, TopicSetInfo.id == TopicSetAttempt.set_info_id).filter(
            TopicSetInfo.subject == subject_key
        )
    mine = attempts_q.order_by(TopicSetAttempt.attempted_at.desc()).all()

    exam_type_key = exam_type.upper().strip()
    out: list[CompletedSetOut] = []
    for a in mine:
        info = db.query(TopicSetInfo).filter(TopicSetInfo.id == a.set_info_id).first()
        if info is None:
            continue
        if "_" in exam_type_key:
            if info.exam_type != exam_type_key:
                continue
        elif not (info.exam_type == exam_type_key or info.exam_type.startswith(f"{exam_type_key}_")):
            continue
        job = db.query(TopicGenerationJob).filter(TopicGenerationJob.id == info.job_id).first()
        if job is None:
            continue
        set_attempts = db.query(TopicSetAttempt).filter(TopicSetAttempt.set_info_id == info.id).all()
        rank_map, takers = _build_set_ranks(set_attempts)
        out.append(
            CompletedSetOut(
                attempted_at=a.attempted_at,
                set=TopicSetOut(
                    id=str(info.id),
                    set_no=info.set_no,
                    exam_type=info.exam_type,
                    subject=info.subject,
                    topic_slug=info.topic_slug,
                    job_id=str(job.id),
                    job_status=job.status.value,
                    num_questions=job.num_questions,
                    created_at=info.created_at,
                    total_takers=takers,
                    attempted_by_me=True,
                    my_rank=rank_map.get(email),
                    my_score=a.score,
                ),
            )
        )

    return CompletedSetListOut(
        exam_type=exam_type_key,
        subject=subject.strip().lower().replace(" ", "_") if subject else None,
        total_completed=len(out),
        completed_sets=out,
    )
