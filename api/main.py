from pathlib import Path

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from api.routers import auth, channels, dashboard, jobs, keyword_graph, linking, links, monitor, posts, reports, settings
from config import settings as app_settings

app = FastAPI(title="TG Post Analyzer Dashboard")

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])
app.include_router(channels.router, prefix="/api/channels", tags=["Channels"])
app.include_router(posts.router, prefix="/api/posts", tags=["Posts"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(monitor.router, prefix="/api/monitor", tags=["Monitor"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["Jobs"])
app.include_router(linking.router, prefix="/api", tags=["Linking"])
app.include_router(links.router, prefix="/api/links", tags=["Links (Deprecated)"])
app.include_router(keyword_graph.router, prefix="/api/keyword", tags=["Keyword Graph"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(app_settings.CORS_ALLOWED_ORIGINS),
    allow_credentials=bool(app_settings.CORS_ALLOW_CREDENTIALS),
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"
FRONTEND_INDEX_FILE = FRONTEND_DIST_DIR / "index.html"
RESERVED_BACKEND_PREFIXES = ("api", "docs", "redoc", "openapi.json")


@app.get("/", include_in_schema=False)
async def frontend_index() -> FileResponse:
    if not FRONTEND_INDEX_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail="Frontend build not found. Run `npm run build` in `frontend/` or start the Vite dev server.",
        )

    return FileResponse(FRONTEND_INDEX_FILE)


@app.get("/{full_path:path}", include_in_schema=False)
async def frontend_spa(full_path: str) -> FileResponse:
    if full_path.startswith(RESERVED_BACKEND_PREFIXES):
        raise HTTPException(status_code=404, detail="Not Found")

    requested_file = FRONTEND_DIST_DIR / full_path
    if full_path and requested_file.is_file():
        return FileResponse(requested_file)

    if full_path and Path(full_path).suffix:
        raise HTTPException(status_code=404, detail="Not Found")

    return await frontend_index()
