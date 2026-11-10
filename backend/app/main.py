from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS
from app import config
from app.database.session import init_db
from app.routes import analysis, gaps, graph, mentor, papers

app = FastAPI(title="ResearchGraph API", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"]
)

init_db()
if config.STORAGE_BACKEND == "local":  # local dev only: re-read PDFs stored before layout-aware extraction (no AI, no data loss)
    try:
        from app.database.session import open_session
        from app.services.reprocess import reprocess_missing

        with open_session() as _db:  # unscoped on purpose: startup maintenance across all rows
            reprocess_missing(_db)
    except Exception:  # never block startup
        pass
app.include_router(papers.router)
app.include_router(analysis.router)
app.include_router(graph.router)
app.include_router(gaps.router)
app.include_router(mentor.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/health/ready")
def ready():
    """Deeper check for deploy smoke tests: DB reachable + AI/embedding config present. Never returns secrets."""
    from sqlalchemy import text

    from app.database.session import engine
    from app.services import ai_client

    try:
        with engine.connect() as c:
            c.execute(text("select 1"))
        db_ok = True
    except Exception:
        db_ok = False
    st = ai_client.status()
    return {"database": db_ok, "ai_configured": st["llm_ready"], "embeddings_configured": st["embedding_ready"],
            "auth": "disabled(dev)" if config.AUTH_DISABLED else ("configured" if config.SUPABASE_URL else "missing"),
            "storage": config.STORAGE_BACKEND}


@app.get("/", include_in_schema=False)
def root():
    from fastapi.responses import HTMLResponse

    return HTMLResponse(
        "<body style='font-family:sans-serif;max-width:560px;margin:60px auto;line-height:1.6'>"
        "<h2>ResearchGraph API is running ✅</h2>"
        "<p>This is the backend. The app you use is the frontend:</p>"
        "<p><b><a href='http://localhost:5173'>http://localhost:5173</a></b> "
        "(start it in a second terminal: <code>cd frontend</code>, <code>npm install</code>, <code>npm run dev</code>)</p>"
        "<p>API docs: <a href='/docs'>/docs</a> · Health: <a href='/api/health'>/api/health</a></p></body>"
    )
