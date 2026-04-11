import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), primary_key=True)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    correct_answer: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    quiz_taken: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total_questions: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    history: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")


class SourceKind(str, enum.Enum):
    RULES = "rules"
    PREVIOUS_YEAR = "previous_year"
    MATERIAL = "material"
    CURRENT_AFFAIRS = "current_affairs"


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    exam_type: Mapped[str] = mapped_column(String(50), index=True)
    subject: Mapped[str] = mapped_column(String(100), default="general", server_default="general")
    kind: Mapped[SourceKind] = mapped_column(Enum(SourceKind), index=True)
    file_path: Mapped[str] = mapped_column(Text, unique=True)
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    is_indexed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    chunks: Mapped[list["SourceChunk"]] = relationship(
        "SourceChunk", back_populates="document", cascade="all, delete-orphan"
    )


class SourceChunk(Base):
    __tablename__ = "source_chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"), index=True)
    exam_type: Mapped[str] = mapped_column(String(50), index=True)
    subject: Mapped[str] = mapped_column(String(100), index=True)
    kind: Mapped[SourceKind] = mapped_column(Enum(SourceKind), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    document: Mapped["SourceDocument"] = relationship("SourceDocument", back_populates="chunks")


class GenerationJob(Base):
    __tablename__ = "generation_jobs"
    __table_args__ = (UniqueConstraint("exam_type", "paper_date", name="uq_exam_date"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    exam_type: Mapped[str] = mapped_column(String(50), index=True)
    paper_size: Mapped[int] = mapped_column(Integer)
    rules_version: Mapped[str] = mapped_column(String(50), default="default", server_default="default")
    paper_date: Mapped[str] = mapped_column(String(10), index=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.QUEUED, index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    message: Mapped[str] = mapped_column(Text, default="", server_default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_affairs_from: Mapped[str | None] = mapped_column(String(10), nullable=True)
    current_affairs_to: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paper_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("question_papers.id"), nullable=True)


class QuestionPaper(Base):
    __tablename__ = "question_papers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    exam_type: Mapped[str] = mapped_column(String(50), index=True)
    paper_number: Mapped[int] = mapped_column(Integer, index=True)
    paper_size: Mapped[int] = mapped_column(Integer)
    rules_version: Mapped[str] = mapped_column(String(50), default="default", server_default="default")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    meta_json: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")

    questions: Mapped[list["QuestionItem"]] = relationship(
        "QuestionItem", back_populates="paper", cascade="all, delete-orphan"
    )


class QuestionItem(Base):
    __tablename__ = "question_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    paper_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("question_papers.id", ondelete="CASCADE"), index=True)
    question_no: Mapped[int] = mapped_column(Integer, index=True)
    subject: Mapped[str] = mapped_column(String(100), index=True)
    topic: Mapped[str] = mapped_column(String(150), default="general", server_default="general")
    question_type: Mapped[str] = mapped_column(String(30), default="mcq", server_default="mcq")
    difficulty: Mapped[str] = mapped_column(String(30), default="medium", server_default="medium")
    question_text: Mapped[str] = mapped_column(Text)
    options_json: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    answer: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text, default="", server_default="")
    marks: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    meta_json: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")

    paper: Mapped["QuestionPaper"] = relationship("QuestionPaper", back_populates="questions")


# ─────────────────────────────────────────────────────────────
#  Topic-wise bilingual question generation
# ─────────────────────────────────────────────────────────────

class TopicSourceKind(str, enum.Enum):
    MATERIAL_EN = "material_en"
    MATERIAL_TA = "material_ta"
    PYQ = "pyq"


class TopicSourceChunk(Base):
    """Vector chunks for topic-scoped documents (en material / ta material / pyq)."""

    __tablename__ = "topic_source_chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    topic_slug: Mapped[str] = mapped_column(String(100), index=True)
    kind: Mapped[TopicSourceKind] = mapped_column(Enum(TopicSourceKind), index=True)
    file_path: Mapped[str] = mapped_column(Text, index=True)
    file_checksum: Mapped[str] = mapped_column(String(64))
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class TopicGenerationJob(Base):
    __tablename__ = "topic_generation_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    topic_slug: Mapped[str] = mapped_column(String(100), index=True)
    num_questions: Mapped[int] = mapped_column(Integer)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.QUEUED, index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    message: Mapped[str] = mapped_column(Text, default="", server_default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TopicSetInfo(Base):
    """
    Metadata for a generated set.
    One generation job == one set for (exam_type, subject, topic_slug).
    """

    __tablename__ = "topic_set_info"
    __table_args__ = (UniqueConstraint("exam_type", "subject", "topic_slug", "set_no", name="uq_topic_set"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("topic_generation_jobs.id", ondelete="CASCADE"), unique=True, index=True
    )
    exam_type: Mapped[str] = mapped_column(String(50), index=True)
    subject: Mapped[str] = mapped_column(String(100), index=True)
    topic_slug: Mapped[str] = mapped_column(String(100), index=True)
    set_no: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class TopicSetAttempt(Base):
    """
    One user can submit one attempt per generated topic set.
    Ranking and set-level leaderboard are derived from this table.
    """

    __tablename__ = "topic_set_attempts"
    __table_args__ = (UniqueConstraint("set_info_id", "user_email", name="uq_set_user_attempt"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    set_info_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("topic_set_info.id", ondelete="CASCADE"), index=True
    )
    user_email: Mapped[str] = mapped_column(
        ForeignKey("users.email", ondelete="CASCADE"), index=True
    )
    score: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    correct_answers: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total_questions: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class ExamBlueprint(Base):
    """Per-exam configuration root (TNPSC / UPSC / etc)."""

    __tablename__ = "exam_blueprints"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    exam_type: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ExamSubjectBlueprint(Base):
    """Subject-level difficulty split + generation hints for each exam type."""

    __tablename__ = "exam_subject_blueprints"
    __table_args__ = (UniqueConstraint("blueprint_id", "subject", name="uq_blueprint_subject"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    blueprint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_blueprints.id", ondelete="CASCADE"), index=True
    )
    subject: Mapped[str] = mapped_column(String(100), index=True)
    easy_pct: Mapped[int] = mapped_column(Integer, default=10, server_default="10")
    moderate_pct: Mapped[int] = mapped_column(Integer, default=20, server_default="20")
    hard_pct: Mapped[int] = mapped_column(Integer, default=70, server_default="70")
    style_json: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class QuestionPattern(Base):
    """Shared anchor that links the English and Tamil versions of the same question."""

    __tablename__ = "question_patterns"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    topic_slug: Mapped[str] = mapped_column(String(100), index=True)
    question_no: Mapped[int] = mapped_column(Integer, index=True)
    difficulty: Mapped[str] = mapped_column(String(30), default="medium", server_default="medium")
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("topic_generation_jobs.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    en_question: Mapped["TopicQuestionEn"] = relationship(
        "TopicQuestionEn", back_populates="pattern", uselist=False, cascade="all, delete-orphan"
    )
    ta_question: Mapped["TopicQuestionTa"] = relationship(
        "TopicQuestionTa", back_populates="pattern", uselist=False, cascade="all, delete-orphan"
    )


class TopicQuestionEn(Base):
    __tablename__ = "topic_questions_en"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    pattern_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question_patterns.id", ondelete="CASCADE"), unique=True, index=True
    )
    topic_slug: Mapped[str] = mapped_column(String(100), index=True)
    question_no: Mapped[int] = mapped_column(Integer, index=True)
    question_text: Mapped[str] = mapped_column(Text)
    options_json: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    answer: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text, default="", server_default="")
    marks: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    pattern: Mapped["QuestionPattern"] = relationship("QuestionPattern", back_populates="en_question")


class TopicQuestionTa(Base):
    __tablename__ = "topic_questions_ta"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    pattern_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question_patterns.id", ondelete="CASCADE"), unique=True, index=True
    )
    topic_slug: Mapped[str] = mapped_column(String(100), index=True)
    question_no: Mapped[int] = mapped_column(Integer, index=True)
    question_text: Mapped[str] = mapped_column(Text)
    options_json: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    answer: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text, default="", server_default="")
    marks: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    pattern: Mapped["QuestionPattern"] = relationship("QuestionPattern", back_populates="ta_question")


class PyqIngestStatus(str, enum.Enum):
    PENDING = "pending"
    INGESTED = "ingested"
    FAILED = "failed"


class PyqSubject(Base):
    __tablename__ = "pyq_subjects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    subject_slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    subject_name: Mapped[str] = mapped_column(String(150))
    icon: Mapped[str] = mapped_column(String(100), default="menu_book", server_default="menu_book")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class PyqDocument(Base):
    __tablename__ = "pyq_documents"
    __table_args__ = (UniqueConstraint("file_path", name="uq_pyq_file_path"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pyq_subjects.id", ondelete="CASCADE"), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(Text)
    year_from: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    year_to: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[PyqIngestStatus] = mapped_column(Enum(PyqIngestStatus), default=PyqIngestStatus.PENDING, index=True)
    total_questions: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class PyqQuestion(Base):
    __tablename__ = "pyq_questions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pyq_documents.id", ondelete="CASCADE"), index=True
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pyq_subjects.id", ondelete="CASCADE"), index=True
    )
    question_no: Mapped[int] = mapped_column(Integer, index=True)
    # Canonical bilingual fields (TNPSC PYQ JSON shape)
    question_en: Mapped[str] = mapped_column(Text, default="", server_default="")
    question_ta: Mapped[str] = mapped_column(Text, default="", server_default="")
    options_en: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    options_ta: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    correct_answer: Mapped[str] = mapped_column(Text, default="", server_default="")
    explanation: Mapped[str] = mapped_column(Text, default="", server_default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    topic: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    exam: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Legacy / combined display (filled on write for older clients)
    question_text_bilingual: Mapped[str] = mapped_column(Text)
    options_json: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    answer_key: Mapped[str] = mapped_column(String(30), default="", server_default="")
    explanation_bilingual: Mapped[str] = mapped_column(Text, default="", server_default="")
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parse_confidence: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    raw_meta_json: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
