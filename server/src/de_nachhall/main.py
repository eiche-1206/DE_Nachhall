"""FastAPI 入口（api 目标）。

异常处理器把三类异常统一渲染成 {"error": {"code", "message"}}：
  ApiError        业务错误，自带面向用户的 code 与 message
  HTTPException   FastAPI 内部抛的（404 路由不存在等）
  RequestValidationError  参数校验，422

不统一的话，前端要为每种形状写一遍解析。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from de_nachhall.config import get_settings
from de_nachhall.db.session import get_engine
from de_nachhall.deps import get_db
from de_nachhall.routers import media, sources, stream
from de_nachhall.schemas.errors import ApiError, error_response

log = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """配置问题在启动时暴露，不留到第一条真实请求。

    实测教训：Settings 原本是第一次要 DB session 时才构造，于是
    /api/health 返回 200、每条数据请求 500，看起来像「服务是好的」。
    """
    get_settings()
    get_engine()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="DE_Nachhall",
    version="0.1.0",
    description="德语听说跟读训练。回声闭环、四层文本、素材导入管线。",
)

# 前端是独立容器（Vite dev server），同源不成立，必须开 CORS。
# 自托管单用户，来源不做白名单没有实际风险。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    # video 的 Range 请求要能读到这两个头，否则前端无法判断服务端是否支持 seek
    expose_headers=["Content-Range", "Accept-Ranges", "Content-Length"],
)


@app.exception_handler(ApiError)
async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message)


@app.exception_handler(StarletteHTTPException)
async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
    return error_response(exc.status_code, code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", ())[1:]) or "请求"
    return error_response(422, "INVALID_REQUEST", f"{field} 不合法：{first.get('msg', '')}")


@app.get("/api/health", tags=["meta"])
def health(db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    """**真的查一次库。** 不碰依赖的健康检查只能证明进程还活着，
    而进程活着恰恰是最不值得报告的那件事 —— 这次就是它让「服务是好的」
    这个判断成立了十八分钟。"""
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


app.include_router(media.router)
app.include_router(sources.router)
app.include_router(stream.router)
