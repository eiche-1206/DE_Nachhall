"""导入、重试、删除。

probe-first（SPEC §5.3）：提交时**同步**跑一次 probe（1–3 秒），
一次拿到能否抓、标题、时长、是否纯音频、平台。代价是提交慢几秒，
换来的是错误即时且准确 —— 否则用户要等三分钟才知道 URL 打错了。
"""

from __future__ import annotations

import logging
import shutil
from datetime import date
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from de_nachhall.db.models import Media, UserMedia
from de_nachhall.ingest.workspace import Workspace
from de_nachhall.ingest.ytdlp import Ytdlp, YtdlpError
from de_nachhall.repositories.jobs import JobsRepository
from de_nachhall.repositories.media import MediaRepository
from de_nachhall.schemas.errors import ApiError

log = logging.getLogger(__name__)

# probe 的失败码 → HTTP 状态。都不是服务端的错，但含义不同：
#   400 用户给错了东西    502 外部站点的问题
_STATUS_BY_CODE = {
    "INVALID_URL": 400,
    "UNSUPPORTED_SITE": 400,
    "AUDIO_NOT_SUPPORTED": 400,
    "PROBE_FAILED": 502,
}


def _to_date(yyyymmdd: str | None) -> date | None:
    if not yyyymmdd or len(yyyymmdd) != 8 or not yyyymmdd.isdigit():
        return None
    try:
        return date(int(yyyymmdd[:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:]))
    except ValueError:
        return None


class IngestService:
    def __init__(self, db: Session, ytdlp: Ytdlp, media_root: Path) -> None:
        self.db = db
        self.ytdlp = ytdlp
        self.media_root = Path(media_root)
        self.media = MediaRepository(db)
        self.jobs = JobsRepository(db)

    # ---------- 导入 ----------

    def import_url(self, url: str, user_id: int) -> tuple[Media, bool]:
        """返回 (media, already_exists)。已存在时不重复转写，只补关联。"""
        url = url.strip()

        existing = self.media.find_by_url(url)
        if existing is not None:
            self.media.link_user_import(user_id, existing.id)
            log.info("url already imported as media %s", existing.id)
            return existing, True

        try:
            probe = self.ytdlp.probe(url)
        except YtdlpError as e:
            raise ApiError(_STATUS_BY_CODE.get(e.code, 502), e.code, e.message) from e

        if not probe.has_video:
            raise ApiError(
                400, "AUDIO_NOT_SUPPORTED", "这是纯音频，暂时不支持。跟读需要画面配合。"
            )

        m = self.media.create(
            source_url=url,
            source_id=None,
            origin="user",
            media_type="video",
            title=probe.title,
            platform=probe.platform,
            duration_ms=probe.duration_ms,
            published_on=_to_date(probe.upload_date),
            status="queued",
        )
        self.media.link_user_import(user_id, m.id)
        # probe 已经拿到了，落盘给 worker 复用，省一次网络往返
        Workspace.for_media(self.media_root, m.id).write_probe(probe.raw)
        self.jobs.enqueue(m.id)
        log.info("imported media %s: %s", m.id, probe.title)
        return m, False

    # ---------- 重试 ----------

    def retry(self, media_id: int) -> Media:
        m = self.db.get(Media, media_id)
        if m is None:
            raise ApiError(404, "NOT_FOUND", "找不到这条素材。")
        if m.status not in ("failed", "ready_partial"):
            raise ApiError(
                409, "NOT_RETRYABLE", f"这条素材当前是「{m.status}」，没有可重试的失败。"
            )

        job = self.jobs.get_by_media(media_id)
        if job is None:
            job = self.jobs.enqueue(media_id)
        else:
            self.jobs.retry_from_failed_stage(job.id)
        self.db.refresh(m)
        log.info("media %s queued for retry from stage %s", media_id, job.stage)
        return m

    # ---------- 删除 ----------

    def delete(self, media_id: int, user_id: int) -> None:
        m = self.db.get(Media, media_id)
        if m is None:
            raise ApiError(404, "NOT_FOUND", "找不到这条素材。")
        if m.origin != "user":
            raise ApiError(
                403, "NOT_DELETABLE",
                "这是订阅源的内容，删不了。要不再看到它，请取消订阅这个源。",
            )

        self.db.execute(
            delete(UserMedia).where(
                UserMedia.user_id == user_id, UserMedia.media_id == media_id
            )
        )
        self.db.commit()

        # 引用计数：还有别人导入过就只解绑，不动文件
        others = self.db.execute(
            select(UserMedia.user_id).where(UserMedia.media_id == media_id)
        ).first()
        if others is not None:
            log.info("media %s still referenced, keeping files", media_id)
            return

        ws = Workspace.for_media(self.media_root, media_id)
        shutil.rmtree(ws.root, ignore_errors=True)
        self.db.delete(m)  # chapters / chunks / job 走 ON DELETE CASCADE
        self.db.commit()
        log.info("media %s deleted with files", media_id)
