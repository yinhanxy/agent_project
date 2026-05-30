# Log Directory

This directory is the shared place for local runtime logs. Keep only the
directory structure and documentation in git; actual log output should stay
ignored.

Suggested module layout:

- `frontend/`: frontend dev server and build logs.
- `backend/`: FastAPI app logs and uvicorn stdout/stderr logs.
- `django/`: Django user service stdout/stderr and Celery logs.
- `ollama/`: Ollama pull or model runtime logs.

When adding a new module, create a matching subdirectory under `log/` and keep
its runtime files out of version control.
