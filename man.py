from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routers import channels, links, monitor, posts, reports

app = FastAPI(title="TG Post Analyzer Dashboard")

app.include_router(channels.router, prefix="/api/channels", tags=["Channels"])
app.include_router(posts.router, prefix="/api/posts", tags=["Posts"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(monitor.router, prefix="/api/monitor", tags=["Monitor"])
app.include_router(links.router, prefix="/api/links", tags=["Links"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = Path(__file__).parent / "web"
if WEB_DIR.exists():
    app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")


@app.get("/", include_in_schema=False)
async def dashboard() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")
