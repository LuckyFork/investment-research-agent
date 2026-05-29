# Agent Console Frontend

## Scope

This frontend is a first-pass `Agent Console` for:

- streaming chat over SSE
- trace list and trace detail viewing
- eval summary and per-case result display

## Local run

1. Start the FastAPI backend on `http://127.0.0.1:8000`
2. Install frontend dependencies inside `frontend/`
3. Run the Vite dev server on `http://127.0.0.1:5173`

The Vite config proxies `/api/*` to the local backend by default.

## Current pages

- `/console`
- `/traces`
- `/traces/:traceId`
- `/evals`

## Notes

- The console uses the current replay/eval APIs from the backend.
- Complex runs automatically refresh the latest trace after the stream completes.
