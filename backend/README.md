## Backend Generation Pipeline

This backend now supports end-to-end question paper generation with:
- PostgreSQL + pgvector
- LangChain + OpenAI (embeddings and LLM)
- RAG over manually provided documents
- Async generation jobs

### 1) Setup

```bash
cd backend
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2) Required document folders

Put your files inside:

- `data/rules/<EXAM_TYPE>/...`
- `data/previous_year/<EXAM_TYPE>/<SUBJECT>/...`
- `data/materials/<EXAM_TYPE>/<SUBJECT>/...`
- `data/current_affairs/<EXAM_TYPE>/<SUBJECT>/...`

Supported file types: `.pdf`, `.txt`, `.md`

Example:

```text
data/
  rules/
    GROUP_1/rules.pdf
  previous_year/
    GROUP_1/polity/pyq_2022.pdf
    GROUP_1/english/pyq_2021.pdf
  materials/
    GROUP_1/polity/laxmikanth_ch1.pdf
  current_affairs/
    GROUP_1/general/current_mar_2026.pdf
```

### 3) Admin-only APIs

All generation APIs require header:

`x-admin-key: <ADMIN_API_KEY>`

Endpoints:

- `POST /generate-paper`
- `GET /generate-paper/{job_id}`
- `GET /papers/{paper_id}`

Sample request:

```bash
curl -X POST "http://127.0.0.1:8000/generate-paper" \
  -H "Content-Type: application/json" \
  -H "x-admin-key: replace-with-strong-admin-key" \
  -d '{
    "exam_type": "GROUP_1",
    "paper_size": 200,
    "rules_version": "2026-v1",
    "force_new": false
  }'
```

### 4) Notes

- Generation is async; poll job endpoint for status.
- By default, one paper per exam type per day unless `force_new=true`.
- Ensure PostgreSQL has `pgvector` extension support.
- Ensure `OPENAI_API_KEY` is set in `.env`.

---

## Individual Subject-wise Bilingual Test Feature

Generates N questions for a single topic (e.g., Indian Polity) in both English and Tamil.
Each question pair shares a common `question_pattern_id` so rankings can be compared across languages.

### Document folder structure

```text
data/
  topics/
    indian_polity/
      en/
        Indian_Polity_english_1st_chapter.pdf   ← English material
      ta/
        Indian_Polity_tamil_1st_chapter.pdf      ← Tamil material
      pyq/
        PYQ_INDIAN_POLITY_2020-2025.pdf          ← PYQ (bilingual)
    another_topic/
      en/ ...
      ta/ ...
      pyq/ ...
```

The `topic_slug` is the folder name (e.g., `indian_polity`).

### Database tables created automatically

| Table | Purpose |
|---|---|
| `topic_source_chunks` | Vector embeddings of topic docs |
| `topic_generation_jobs` | Job tracking for topic generation |
| `question_patterns` | Shared row linking EN + TA question (holds `question_pattern_id`) |
| `topic_questions_en` | English version of each question |
| `topic_questions_ta` | Tamil version of each question |

### Admin-only: Generate questions

```bash
curl -X POST "http://127.0.0.1:8000/generate-topic-questions" \
  -H "Content-Type: application/json" \
  -H "x-admin-key: replace-with-strong-admin-key" \
  -d '{
    "topic_slug": "indian_polity",
    "num_questions": 50
  }'
```

Response:
```json
{"job_id": "<uuid>", "topic_slug": "indian_polity", "status": "queued", "message": "Topic question generation started"}
```

### Poll job status

```bash
curl "http://127.0.0.1:8000/generate-topic-questions/<job_id>" \
  -H "x-admin-key: replace-with-strong-admin-key"
```

### Fetch questions (authenticated users)

English:
```bash
curl "http://127.0.0.1:8000/topics/indian_polity/questions?lang=en" \
  -H "Authorization: Bearer <user_jwt>"
```

Tamil:
```bash
curl "http://127.0.0.1:8000/topics/indian_polity/questions?lang=ta" \
  -H "Authorization: Bearer <user_jwt>"
```

Response includes `question_pattern_id` on every question — use this to join EN and TA rows for ranking comparison.
