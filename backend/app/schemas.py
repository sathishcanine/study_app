from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str | None = None


class GoogleAuthIn(BaseModel):
    id_token: str = Field(min_length=10)


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    username: str = Field(min_length=1, max_length=255)
    score: int = 0


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class QuizResultIn(BaseModel):
    score: int
    question_numbers: int
    correct_answers: int
    cat_name: str
    question_length: int
    difficulty: str
    date: datetime


class LeaderboardEntry(BaseModel):
    username: str
    score: int


class GeneratePaperIn(BaseModel):
    exam_type: str = Field(min_length=2, max_length=50)
    paper_size: int = Field(default=200, ge=50, le=300)
    rules_version: str = Field(default="default", max_length=50)
    current_affairs_date_from: str | None = None
    current_affairs_date_to: str | None = None
    force_new: bool = False


class JobQueuedOut(BaseModel):
    job_id: str
    status: str
    message: str


class JobStatusOut(BaseModel):
    job_id: str
    status: str
    progress: int
    exam_type: str
    paper_size: int
    paper_id: str | None
    message: str
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class QuestionOut(BaseModel):
    question_no: int
    subject: str
    topic: str
    question_type: str
    difficulty: str
    question_text: str
    options: list[str]
    answer: str
    explanation: str
    marks: int


class PaperOut(BaseModel):
    paper_id: str
    exam_type: str
    paper_number: int
    paper_size: int
    rules_version: str
    created_at: datetime
    questions: list[QuestionOut]


# ── Topic-wise bilingual test schemas ───────────────────────────

class GenerateTopicQuestionsIn(BaseModel):
    exam_type: str = Field(
        min_length=2,
        max_length=50,
        description="Exam family like TNPSC_GROUP1, UPSC_PRELIMS",
    )
    subject: str = Field(
        min_length=2,
        max_length=100,
        description="Fixed subject name for the exam, e.g. polity",
    )
    topic_slug: str = Field(
        min_length=2,
        max_length=100,
        description="Folder name under data/topics/ e.g. 'indian_polity'",
    )
    num_questions: int = Field(
        default=50,
        ge=5,
        le=300,
        description="Number of questions to generate (same count per language)",
    )


class TopicJobQueuedOut(BaseModel):
    job_id: str
    set_no: int
    exam_type: str
    subject: str
    topic_slug: str
    status: str
    message: str


class TopicJobStatusOut(BaseModel):
    job_id: str
    set_no: int | None = None
    exam_type: str | None = None
    subject: str | None = None
    topic_slug: str
    num_questions: int
    status: str
    progress: int
    message: str
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class TopicQuestionOut(BaseModel):
    question_pattern_id: str
    set_no: int | None = None
    exam_type: str | None = None
    subject: str | None = None
    question_no: int
    difficulty: str
    language: str
    question_text: str
    options: list[str]
    answer: str
    explanation: str
    marks: int


class TopicQuestionsOut(BaseModel):
    set_no: int | None = None
    exam_type: str | None = None
    subject: str | None = None
    topic_slug: str
    language: str
    total: int
    questions: list[TopicQuestionOut]


class TopicSetOut(BaseModel):
    set_no: int
    exam_type: str
    subject: str
    topic_slug: str
    job_id: str
    job_status: str
    num_questions: int
    created_at: datetime


class TopicSetListOut(BaseModel):
    exam_type: str
    subject: str
    topic_slug: str
    total_sets: int
    sets: list[TopicSetOut]
