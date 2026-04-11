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
    id: str
    set_no: int
    exam_type: str
    subject: str
    topic_slug: str
    job_id: str
    job_status: str
    num_questions: int
    created_at: datetime
    total_takers: int = 0
    attempted_by_me: bool = False
    my_rank: int | None = None
    my_score: int | None = None


class TopicSetListOut(BaseModel):
    exam_type: str
    subject: str
    topic_slug: str
    total_sets: int
    sets: list[TopicSetOut]


class SubjectSetListOut(BaseModel):
    exam_type: str
    subject: str
    total_sets: int
    sets: list[TopicSetOut]


class TopicSetAttemptIn(BaseModel):
    score: int = Field(ge=0)
    correct_answers: int = Field(ge=0)
    total_questions: int = Field(ge=1)


class TopicSetAttemptOut(BaseModel):
    set_id: str
    user_email: str
    score: int
    correct_answers: int
    total_questions: int
    rank: int
    total_takers: int
    attempted_at: datetime


class SetLeaderboardEntry(BaseModel):
    rank: int
    email: str
    username: str
    score: int
    correct_answers: int
    total_questions: int
    attempted_at: datetime


class SetLeaderboardOut(BaseModel):
    set_id: str
    exam_type: str
    subject: str
    topic_slug: str
    set_no: int
    total_takers: int
    entries: list[SetLeaderboardEntry]


class CompletedSetOut(BaseModel):
    set: TopicSetOut
    attempted_at: datetime


class CompletedSetListOut(BaseModel):
    exam_type: str
    subject: str | None = None
    total_completed: int
    completed_sets: list[CompletedSetOut]


class PyqSubjectOut(BaseModel):
    subject_slug: str
    subject_name: str
    total_questions: int
    total_documents: int


class PyqSubjectListOut(BaseModel):
    total_subjects: int
    subjects: list[PyqSubjectOut]


class PyqFiltersOut(BaseModel):
    subject_slug: str
    years: list[int]
    topics: list[str] = Field(description="Distinct `topic` values from questions.")
    subtopics: list[str] = Field(
        default_factory=list,
        description="Same list as topics; kept for older clients.",
    )


class PyqQuestionOut(BaseModel):
    id: str
    question_no: int
    question_en: str = ""
    question_ta: str = ""
    options_en: list[str] = Field(default_factory=list)
    options_ta: list[str] = Field(default_factory=list)
    correct_answer: str = ""
    explanation: str = ""
    exam: str | None = None
    year: int | None = None
    topic: str | None = None
    question_text_bilingual: str
    options: list[str]
    answer_key: str
    answer_display: str = Field(
        default="",
        description="Same as correct_answer when set; else legacy short key.",
    )
    explanation_bilingual: str
    subtopic: str | None = Field(default=None, description="Alias of topic for older clients.")
    exam_name: str | None = Field(default=None, description="Alias of exam for older clients.")
    content_source: str | None = Field(
        default=None,
        description="openai_* or legacy ocr/pypdf from raw_meta_json when present.",
    )


class PyqQuestionPageOut(BaseModel):
    subject_slug: str
    total: int
    page: int
    limit: int
    questions: list[PyqQuestionOut]


class PyqManualQuestionIn(BaseModel):
    """One MCQ row for POST /admin/pyq/import-json (typed from ChatGPT or a spreadsheet)."""

    question_text: str = Field(..., min_length=1)
    question_en: str | None = None
    question_ta: str | None = None
    options: list[str] = Field(..., min_length=2)
    options_en: list[str] | None = None
    options_ta: list[str] | None = None
    answer: str = Field(..., min_length=1)
    year: int | None = None
    topic: str | None = None
    subtopic: str | None = None
    exam: str | None = None
    exam_name: str | None = None
    explanation: str = ""


class PyqImportJsonIn(BaseModel):
    subject_slug: str = Field(..., min_length=1)
    replace_subject_questions: bool = Field(
        default=False,
        description="If true, deletes all existing PYQ rows for this subject before insert.",
    )
    questions: list[PyqManualQuestionIn] = Field(..., min_length=1)


class PyqPasteTextIn(BaseModel):
    subject_slug: str = Field(..., min_length=1)
    raw_text: str = Field(..., min_length=20)
    append: bool = Field(default=True, description="If false, clears subject questions first.")
    max_questions: int = Field(default=40, ge=1, le=500)
