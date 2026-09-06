"""TTS Studio 后端入口。"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .api import export_api, jobs, llm_api, pronunciations, providers, settings, tasks, tts, voices
from .config import AUDIO_DIR, DATA_DIR, FRONTEND_DIST, ensure_dirs
from .services import audio as audio_svc

logger = logging.getLogger("tts-studio")


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    await db.init_db()
    # 崩溃恢复：把中断的合成句复位为 pending（已完成句子不动，天然断点续用）
    async with db.connect() as conn:
        await conn.execute("UPDATE lines SET status='pending' WHERE status='synthesizing'")
    if audio_svc.ffmpeg_available():
        logger.info("ffmpeg: %s", audio_svc.find_ffmpeg())
    else:
        logger.warning("未检测到 ffmpeg：合并导出/SRT/变速功能不可用（单句合成不受影响）")
    yield


def create_app() -> FastAPI:
    ensure_dirs()  # 静态目录挂载前必须存在（lifespan 里会再初始化数据库）
    app = FastAPI(title="TTS Studio", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )
    app.include_router(providers.router)
    app.include_router(settings.router)
    app.include_router(tts.router)
    app.include_router(voices.router)
    app.include_router(tasks.router)
    app.include_router(jobs.router)
    app.include_router(export_api.router)
    app.include_router(llm_api.router)
    app.include_router(pronunciations.router)

    @app.get("/api/system/status", tags=["system"])
    async def system_status():
        return {"ffmpeg": audio_svc.ffmpeg_available(), "data_dir": str(DATA_DIR)}

    app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")

    # 生产模式：托管前端构建产物（单端口部署）
    if FRONTEND_DIST.exists():
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            target = FRONTEND_DIST / path
            if path and target.is_file():
                return FileResponse(target)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()
