from fastapi import FastAPI
from api.routers import channels, posts, reports, monitor
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="TG Post Analyzer Dashboard")

app.include_router(channels.router, prefix="/api/channels", tags=["Channels"])
app.include_router(posts.router, prefix="/api/posts", tags=["Posts"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(monitor.router, prefix="/api/monitor", tags=["Monitor"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
