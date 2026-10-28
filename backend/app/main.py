from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import settings, ROOT
from .db import init_db
from . import auth, profile, billing, notify, api, orchestrator
from .mockportal import router as portal_router

app = FastAPI(title="AutoJopps prototype v1", version="0.1")
for r in (auth.router, profile.router, billing.router, notify.router, api.router, portal_router):
    app.include_router(r)

DIST = ROOT / "frontend" / "dist"


@app.on_event("startup")
def _startup():
    init_db()
    orchestrator.start()
    print("AutoJopps modes:", settings.modes())


@app.get("/api/health")
def health():
    return {"ok": True, "modes": settings.modes()}


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", response_class=HTMLResponse)
    def spa(path: str):
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
else:
    @app.get("/", response_class=HTMLResponse)
    def no_ui():
        return "<h2>AutoJopps API is up.</h2><p>Build the frontend (cd frontend && npm install && npm run build) or run it with npm run dev.</p>"
