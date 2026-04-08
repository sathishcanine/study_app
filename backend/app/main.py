import secrets
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth_utils import create_access_token, decode_token, get_user_by_email, hash_password, verify_password
from app.database import Base, engine, get_db
from app.models import User
from app.google_verify import verify_google_id_token
from app.schemas import GoogleAuthIn, LeaderboardEntry, QuizResultIn, TokenResponse, UserLogin, UserRegister

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
