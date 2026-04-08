from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

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
