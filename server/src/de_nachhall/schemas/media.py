"""素材相关的请求与响应。

两条来自 PRD 的硬约束写在类型里，不靠约定：
  1. 列表项**没有** chunk_count —— 首页只谈时长（PRD F1.2、UI-SPEC L1）。
     字段不存在，前端就没法把它渲染出来。
  2. ready_partial 的素材 chunks 有值而 chapters 为空 —— 所以 chapters
     是 list 而不是 Optional，空列表就是「还没分章」的正常状态。
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

ORM = ConfigDict(from_attributes=True)


# ==================== 进度 ====================


class JobStatus(BaseModel):
    """处理中素材的进度。前端 2 秒轮询读它。"""

    model_config = ORM

    stage: str = Field(examples=["transcribing"])
    percent: int = Field(ge=0, le=100)
    error_code: str | None = None
    error_detail: str | None = None
    attempt: int = 0
    updated_at: datetime | None = None


# ==================== 列表 ====================


class MediaListItem(BaseModel):
    """首页时间线的一项。**不含 chunk_count** —— 首页只谈时长。"""

    model_config = ORM

    id: int
    title: str
    published_on: date | None = None
    duration_ms: int | None = None
    platform: str | None = None
    origin: str
    status: str
    thumb_path: str | None = None
    job: JobStatus | None = None


class MediaListResponse(BaseModel):
    items: list[MediaListItem]


# ==================== 详情 ====================


class ChunkOut(BaseModel):
    """训练单元。翻译是其覆盖句子的翻译拼接，未完成时为 None。"""

    model_config = ORM

    idx: int
    chapter_idx: int
    start_ms: int
    end_ms: int
    text: str
    word_count: int
    translation_zh: str | None = None


class ChapterOut(BaseModel):
    model_config = ORM

    idx: int
    title: str | None = None
    start_ms: int
    end_ms: int
    chunk_count: int


class MediaDetail(MediaListItem):
    source_url: str
    # ready_partial 时为空列表 —— 还没分章，但下面的 chunks 已可跟读
    chapters: list[ChapterOut] = []
    chunk_count: int = 0


class ChunksResponse(BaseModel):
    media_id: int
    chunks: list[ChunkOut]


# ==================== 导入 ====================


class ImportRequest(BaseModel):
    url: str = Field(
        min_length=8,
        examples=["https://www.logo.de/logo-vom-freitag-21-august-2026-100.html"],
    )


class ImportResponse(BaseModel):
    """probe 已同步跑完，所以这里的标题与时长是真的，不是占位。"""

    media_id: int
    title: str
    duration_ms: int | None = None
    platform: str | None = None
    # True = 这条 URL 之前就导过，不会重复转写，前端直接跳转
    already_exists: bool = False


# ==================== 订阅源 ====================


class SourceOut(BaseModel):
    model_config = ORM

    id: int
    name: str
    kind: str
    channel_url: str | None = None


class SourcesResponse(BaseModel):
    items: list[SourceOut]
