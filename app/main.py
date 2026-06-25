from __future__ import annotations

from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.auth import clear_session_cookie, require_user, set_session_cookie, verify_credentials
from app.rag.answerer import answer_question
from app.rag.indexing import index_exists, load_index
from app.rag.retriever import Retriever
from app.settings import Settings


ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "app" / "static"
HTML_DIR = ROOT / "html"


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings()
    app = FastAPI(title="TKE RAG Challenge", version="1.0.0")
    app.state.settings = app_settings
    app.state.retriever = _load_retriever(app_settings)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    if HTML_DIR.exists():
        app.mount("/challenge", StaticFiles(directory=HTML_DIR, html=True), name="challenge")

    def authed_user(request: Request) -> str:
        return require_user(request, app_settings)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.post("/api/login")
    def login(payload: LoginRequest, response: Response) -> dict[str, str]:
        if not verify_credentials(payload.username, payload.password, app_settings):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        set_session_cookie(response, payload.username, app_settings)
        return {"status": "ok"}

    @app.post("/api/logout")
    def logout(response: Response) -> dict[str, str]:
        clear_session_cookie(response)
        return {"status": "ok"}

    @app.get("/api/health")
    def health() -> dict[str, object]:
        retriever = app.state.retriever
        return {
            "status": "ok",
            "index_ready": retriever is not None,
            "chunk_count": len(retriever.index.chunks) if retriever else 0,
        }

    @app.post("/api/chat")
    def chat(
        payload: ChatRequest,
        user: str = Depends(authed_user),
    ) -> dict[str, object]:
        retriever: Retriever | None = app.state.retriever
        if retriever is None:
            raise HTTPException(
                status_code=503,
                detail="RAG index is not ready. Run scripts.crawl and scripts.build_index first.",
            )

        results = retriever.search(payload.message, top_k=app_settings.rag_top_k)
        answer = answer_question(
            payload.message,
            results,
            ollama_base_url=app_settings.ollama_base_url,
            ollama_model=app_settings.ollama_model,
            max_context_chars=app_settings.rag_max_context_chars,
        )
        return {
            "answer": answer.answer,
            "mode": answer.mode,
            "sources": [source.__dict__ for source in answer.sources],
        }

    return app


def _load_retriever(settings: Settings) -> Retriever | None:
    if not index_exists(settings.index_dir):
        return None
    return Retriever(load_index(settings.index_dir))


app = create_app()
