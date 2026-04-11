"""One-time additive / rename migrations for PYQ tables (no Alembic in this project)."""

from sqlalchemy import text
from sqlalchemy.engine import Connection


def ensure_pyq_question_schema(conn: Connection) -> None:
    conn.execute(
        text(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'pyq_questions' AND column_name = 'exam_name'
              ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'pyq_questions' AND column_name = 'exam'
              ) THEN
                ALTER TABLE pyq_questions RENAME COLUMN exam_name TO exam;
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'pyq_questions' AND column_name = 'subtopic'
              ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'pyq_questions' AND column_name = 'topic'
              ) THEN
                ALTER TABLE pyq_questions RENAME COLUMN subtopic TO topic;
              END IF;
            END $$;
            """
        )
    )
    for ddl in (
        "ALTER TABLE pyq_questions ADD COLUMN IF NOT EXISTS question_en TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE pyq_questions ADD COLUMN IF NOT EXISTS question_ta TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE pyq_questions ADD COLUMN IF NOT EXISTS options_en JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE pyq_questions ADD COLUMN IF NOT EXISTS options_ta JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE pyq_questions ADD COLUMN IF NOT EXISTS correct_answer TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE pyq_questions ADD COLUMN IF NOT EXISTS explanation TEXT NOT NULL DEFAULT ''",
    ):
        conn.execute(text(ddl))

    conn.execute(
        text(
            """
            UPDATE pyq_questions
            SET explanation = TRIM(explanation_bilingual)
            WHERE (explanation IS NULL OR TRIM(explanation) = '')
              AND explanation_bilingual IS NOT NULL
              AND TRIM(explanation_bilingual) <> '';
            """
        )
    )
