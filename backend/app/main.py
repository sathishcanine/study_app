import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.auth_utils import create_access_token, decode_token, get_user_by_email, hash_password, verify_password
from app.config import settings
from app.database import Base, SessionLocal, engine, get_db
from app.generate_pipeline import run_generation_job, to_job_status, to_paper_out
from app.google_verify import verify_google_id_token
from app.models import GenerationJob, JobStatus, QuestionPaper, QuestionPattern, TopicGenerationJob, User
from app.schemas import (
    GeneratePaperIn,
    GenerateTopicQuestionsIn,
    GoogleAuthIn,
    JobQueuedOut,
    JobStatusOut,
    LeaderboardEntry,
    PaperOut,
    QuizResultIn,
    TokenResponse,
    TopicJobQueuedOut,
    TopicJobStatusOut,
    TopicQuestionsOut,
    UserLogin,
    UserRegister,
)
from app.topic_pipeline import run_topic_generation_job, topic_job_to_dict, topic_questions_to_dict

security = HTTPBearer(auto_error=False)


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
    hist = list(user.history) if user.history else []
    hist.append(
        {
            "catName": body.cat_name,
            "correctQuestions": body.correct_answers,
            "difficulty": body.difficulty,
            "earnedPoints": body.score,
            "questionNumbers": body.question_length,
            "date": body.date.isoformat(),
        }
    )
    user.score = user.score + body.score
    user.total_questions = user.total_questions + body.question_numbers
    user.quiz_taken = user.quiz_taken + 1
    user.correct_answer = user.correct_answer + body.correct_answers
    user.history = hist
    db.commit()
    return user_profile_dict(user)


@app.get("/leaderboard", response_model=list[LeaderboardEntry])
def leaderboard(db: Session = Depends(get_db)):
    rows = db.query(User).order_by(User.score.desc()).all()
    return [LeaderboardEntry(username=u.username, score=u.score) for u in rows]


@app.get("/health")
def health():
    return {"ok": True}


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
    running = (
        db.query(TopicGenerationJob)
        .filter(
            TopicGenerationJob.topic_slug == body.topic_slug,
            TopicGenerationJob.status.in_([JobStatus.QUEUED, JobStatus.PROCESSING]),
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
    return TopicJobStatusOut(**topic_job_to_dict(job))


@app.get("/topics/{topic_slug}/questions", response_model=TopicQuestionsOut)
def get_topic_questions(
    topic_slug: str,
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

    patterns = (
        db.query(QuestionPattern)
        .filter(QuestionPattern.topic_slug == topic_slug)
        .order_by(QuestionPattern.question_no)
        .all()
    )
    if not patterns:
        raise HTTPException(
            status_code=404,
            detail=f"No questions found for topic '{topic_slug}'. Generate them first.",
        )

    questions = topic_questions_to_dict(patterns, lang)
    return TopicQuestionsOut(
        topic_slug=topic_slug,
        language=lang,
        total=len(questions),
        questions=questions,
    )
