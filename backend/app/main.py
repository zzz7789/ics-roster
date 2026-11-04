"""FastAPI 应用入口。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import CORS_ORIGINS, FRONTEND_DIST
from .db import init_db
from .routers import calendar, shifts
from .seed import seed_defaults


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_defaults()
    yield


app = FastAPI(
    title="ics-roster",
    description="多人排班的 ICS 生成、上传与可视化服务",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(shifts.router)
app.include_router(calendar.router)


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "ics-roster"}


# 单容器部署：前端构建产物放在 backend/static 时直接托管
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="static")
