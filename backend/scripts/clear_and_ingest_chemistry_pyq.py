#!/usr/bin/env python3
"""
Delete all stored PYQ questions for chemistry, then re-extract from
`data/previous_year/chemistry__pyq__2020_2025.pdf` (and any other chemistry PDF rows) via OpenAI.

Run from repository root:
  cd backend && python scripts/clear_and_ingest_chemistry_pyq.py

Requires: Postgres (DATABASE_URL / .env), OPENAI_API_KEY, PDF on disk.
"""
from __future__ import annotations

import os
import sys

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)
os.chdir(BACKEND_ROOT)

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import PyqIngestStatus, PyqQuestion, PyqSubject, PyqDocument  # noqa: E402
from app.pyq_pipeline import ingest_subject_with_openai, sync_pyq_catalog_from_files  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        sync_pyq_catalog_from_files(db)
        subject = db.query(PyqSubject).filter(PyqSubject.subject_slug == "chemistry").first()
        if subject is None:
            print("Subject chemistry not found. Add backend/data/previous_year/chemistry__pyq__2020_2025.pdf and restart.")
            raise SystemExit(1)

        deleted = db.query(PyqQuestion).filter(PyqQuestion.subject_id == subject.id).delete(
            synchronize_session=False
        )
        for doc in db.query(PyqDocument).filter(PyqDocument.subject_id == subject.id).all():
            doc.total_questions = 0
            doc.status = PyqIngestStatus.PENDING
        db.commit()
        print(f"Cleared {deleted} chemistry question(s); documents reset to pending.")

        if not (settings.openai_api_key or "").strip():
            print("Set OPENAI_API_KEY in backend/.env before ingesting.")
            raise SystemExit(2)

        summary = ingest_subject_with_openai(db, "chemistry", max_questions=450)
        print("Ingest finished:", summary)
    finally:
        db.close()


if __name__ == "__main__":
    main()
