"""素材路由：时间线、详情、chunks、导入、重试、删除。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from de_nachhall.config import Settings
from de_nachhall.db.models import Chapter, Chunk, Media, Sentence
from de_nachhall.deps import current_user_id, get_db, settings
from de_nachhall.ingest.ytdlp import Ytdlp
from de_nachhall.repositories.media import MediaRepository
from de_nachhall.schemas.errors import ERROR_RESPONSES, ApiError
from de_nachhall.schemas.media import (
    ChapterOut,
    ChunkOut,
    ChunksResponse,
    ImportRequest,
    ImportResponse,
    JobStatus,
    MediaDetail,
    MediaListItem,
    MediaListResponse,
)
from de_nachhall.services.ingest_service import IngestService

router = APIRouter(prefix="/api/media", tags=["media"], responses=ERROR_RESPONSES)

DB = Annotated[Session, Depends(get_db)]
UID = Annotated[int, Depends(current_user_id)]
CFG = Annotated[Settings, Depends(settings)]


def _service(db: Session, cfg: Settings) -> IngestService:
    return IngestService(db, Ytdlp(proxy=cfg.https_proxy), cfg.media_root)


def _item(m: Media) -> MediaListItem:
    return MediaListItem(
        id=m.id,
        title=m.title,
        published_on=m.published_on,
        duration_ms=m.duration_ms,
        platform=m.platform,
        origin=m.origin,
        status=m.status,
        thumb_path=m.thumb_path,
        job=JobStatus.model_validate(m.job) if m.job and m.status != "ready" else None,
    )


# ==================== 查询 ====================


@router.get("", response_model=MediaListResponse, summary="时间线")
def list_media(
    db: DB,
    uid: UID,
    status: Annotated[list[str] | None, Query(description="按状态筛选，可多个")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> MediaListResponse:
    """订阅源与自行导入**混排在一条时间线**上，不分 Tab（PRD A9）。"""
    repo = MediaRepository(db)
    rows = repo.by_status(uid, status) if status else repo.timeline(uid, limit=limit)
    return MediaListResponse(items=[_item(m) for m in rows[:limit]])


@router.get("/{media_id}", response_model=MediaDetail, summary="详情")
def get_media(media_id: int, db: DB) -> MediaDetail:
    m = MediaRepository(db).detail(media_id)
    if m is None:
        raise ApiError(404, "NOT_FOUND", "找不到这条素材。")

    # 只有带标题的章节才是「真的分过章」。转写阶段写的是一个覆盖全片的
    # 占位章（title=None），LLM 降级后也是同一形态 —— 两者对前端的含义
    # 相同：没有可展示的新闻条目，但下面的 chunks 已经可以跟读。
    chapters = [
        ChapterOut(
            idx=ch.idx,
            title=ch.title,
            start_ms=ch.start_ms,
            end_ms=ch.end_ms,
            chunk_count=len(ch.chunks),
        )
        for ch in m.chapters
        if ch.title is not None
    ]
    total = db.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.media_id == media_id)
    )
    return MediaDetail(
        **_item(m).model_dump(),
        source_url=m.source_url,
        chapters=chapters,
        chunk_count=int(total or 0),
    )


@router.get("/{media_id}/chunks", response_model=ChunksResponse, summary="全部 chunk")
def get_chunks(media_id: int, db: DB) -> ChunksResponse:
    """回声页一次取全 —— 53 段总共几十 KB，逐段拉只会在切段时卡顿。"""
    if db.get(Media, media_id) is None:
        raise ApiError(404, "NOT_FOUND", "找不到这条素材。")

    # 翻译挂在 sentence 层，chunk 的翻译是其覆盖句子的拼接（SPEC §3.4）
    zh = {
        idx: text
        for idx, text in db.execute(
            select(Sentence.idx, Sentence.translation_zh).where(
                Sentence.media_id == media_id, Sentence.translation_zh.isnot(None)
            )
        )
    }
    rows = db.execute(
        select(Chunk, Chapter.idx)
        .join(Chapter, Chunk.chapter_id == Chapter.id)
        .where(Chunk.media_id == media_id)
        .order_by(Chunk.idx)
    ).all()

    out: list[ChunkOut] = []
    for c, chapter_idx in rows:
        parts = [zh[i] for i in range(c.start_sentence_idx, c.end_sentence_idx + 1) if i in zh]
        out.append(
            ChunkOut(
                idx=c.idx,
                chapter_idx=chapter_idx,
                start_ms=c.start_ms,
                end_ms=c.end_ms,
                text=c.text,
                word_count=c.word_count,
                translation_zh="".join(parts) or None,
            )
        )
    return ChunksResponse(media_id=media_id, chunks=out)


# ==================== 写入 ====================


@router.post("", response_model=ImportResponse, summary="导入 URL（同步 probe）")
def import_media(body: ImportRequest, db: DB, uid: UID, cfg: CFG) -> ImportResponse:
    """probe 同步执行（1–3 秒）。慢这几秒，换 URL 打错时立刻知道。"""
    m, existed = _service(db, cfg).import_url(body.url, uid)
    return ImportResponse(
        media_id=m.id,
        title=m.title,
        duration_ms=m.duration_ms,
        platform=m.platform,
        already_exists=existed,
    )


@router.post("/{media_id}/retry", response_model=MediaListItem, summary="从失败阶段续跑")
def retry_media(media_id: int, db: DB, cfg: CFG) -> MediaListItem:
    """已完成阶段的产物复用：mp4 下过不重下，wav 抽过不重抽。"""
    return _item(_service(db, cfg).retry(media_id))


@router.delete("/{media_id}", status_code=204, summary="删除（仅自行导入）")
def delete_media(media_id: int, db: DB, uid: UID, cfg: CFG) -> None:
    _service(db, cfg).delete(media_id, uid)
