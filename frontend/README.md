# Frontend

## Status

**Implemented (v1.0).** A minimal Streamlit frontend is available at `frontend/app.py`.

## Running the Frontend

Start the backend first:

```bash
cd backend
uvicorn app.main:app --reload
```

Then in a second terminal (from the repo root):

```bash
streamlit run frontend/app.py
```

The UI will open at `http://localhost:8501`.

## Features

- Upload documents (TXT, Markdown, PDF, DOCX) and see indexing status
- Enter a natural-language question and receive an AI-generated answer
- See retrieved source chunks with document IDs, chunk IDs, and relevance scores
- Handles empty retrieval, API errors, and backend unavailability clearly
- Backend health status displayed on load

## What It Does NOT Do

- Authentication
- Persistent session history
- Duplicate backend logic (all processing done server-side)
- Agent workflows, memory, or knowledge graph features

## Configuration

The frontend connects to `http://127.0.0.1:8000` by default.
Edit the `API_BASE` constant at the top of `app.py` to point to a different backend URL.

## Dependencies

`streamlit` must be installed:

```bash
pip install streamlit
```
