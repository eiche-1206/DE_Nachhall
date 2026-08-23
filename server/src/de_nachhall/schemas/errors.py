"""统一错误形状。

所有路由共用一个模型，前端只写一次错误处理分支。

message 面向用户，且必须**说明怎么修**（PRD F3.2.5）——
"抓取失败" 是没用的，"这个视频需要登录才能看" 才让人知道下一步做什么。
code 给前端做分支判断，不展示。
"""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str = Field(examples=["UNSUPPORTED_SITE"])
    message: str = Field(examples=["这个站点抓不了。支持 YouTube、ZDF、ARD 等常见视频站。"])


class ErrorResponse(BaseModel):
    error: ErrorBody


class ApiError(HTTPException):
    """抛它，异常处理器会渲染成 ErrorResponse 的形状。"""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


# 挂在路由的 responses= 上，让 /openapi.json 里每个错误码都有形状
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorResponse, "description": "请求本身有问题"},
    403: {"model": ErrorResponse, "description": "不允许的操作"},
    404: {"model": ErrorResponse, "description": "找不到"},
    409: {"model": ErrorResponse, "description": "与当前状态冲突"},
    422: {"model": ErrorResponse, "description": "参数校验失败"},
    502: {"model": ErrorResponse, "description": "外部依赖失败"},
}
