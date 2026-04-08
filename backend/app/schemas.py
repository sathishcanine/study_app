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
