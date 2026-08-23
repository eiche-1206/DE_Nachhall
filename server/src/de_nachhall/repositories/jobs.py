"""任务队列的数据访问。

**换数据库时只需要改这个文件。** SQLite 与 Postgres 的出队原语不同：

    SQLite     单 worker，普通 UPDATE ... WHERE id = (SELECT ... LIMIT 1)
    Postgres   多 worker，SELECT ... FOR UPDATE SKIP LOCKED

MVP 只有一个 worker，不存在争抢，所以 SQLite 够用（SPEC §1.1）。
把差异关在这一层，是为了让「以后换 Postgres」真的只是换实现。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from de_nachhall.db.models import IngestJob, Media

# worker 崩溃后，锁超过这个时间的任务会被重新捡起
LOCK_TIMEOUT = timedelta(minutes=15)

ACTIVE_STAGES = ("queued", "downloading", "transcoding", "transcribing", "enriching")


def _now() -> datetime:
    return datetime.now(UTC)


class JobsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------- 入队 ----------

    def enqueue(self, media_id: int) -> IngestJob:
        job = IngestJob(media_id=media_id, stage="queued", percent=0)
        self.db.add(job)
        self.db.commit()
        return job

    def get_by_media(self, media_id: int) -> IngestJob | None:
        return self.db.execute(
            select(IngestJob).where(IngestJob.media_id == media_id)
        ).scalar_one_or_none()

    # ---------- 出队 ----------

    def claim_next(self) -> IngestJob | None:
        """取一个待办任务并加锁。无任务时返回 None。

        单 worker 下无需 SKIP LOCKED：UPDATE 本身是原子的，
        WHERE 里带上 locked_at 条件即可保证同一行不会被取两次。
        """
        cutoff = _now() - LOCK_TIMEOUT

        candidate = self.db.execute(
            select(IngestJob.id)
            .where(
                IngestJob.stage.in_(ACTIVE_STAGES),
                (IngestJob.locked_at.is_(None)) | (IngestJob.locked_at < cutoff),
            )
            .order_by(IngestJob.id)
            .limit(1)
        ).scalar_one_or_none()
        if candidate is None:
            return None

        # 带条件的 UPDATE：若已被别人抢走，rowcount 为 0
        result: CursorResult[Any] = self.db.execute(  # type: ignore[assignment]
            update(IngestJob)
            .where(
                IngestJob.id == candidate,
                (IngestJob.locked_at.is_(None)) | (IngestJob.locked_at < cutoff),
            )
            .values(locked_at=_now(), attempt=IngestJob.attempt + 1)
        )
        self.db.commit()
        if result.rowcount == 0:
            return None
        return self.db.get(IngestJob, candidate)

    def release(self, job_id: int) -> None:
        self.db.execute(update(IngestJob).where(IngestJob.id == job_id).values(locked_at=None))
        self.db.commit()

    # ---------- 阶段推进 ----------

    def set_stage(self, job_id: int, stage: str, percent: int = 0) -> None:
        self.db.execute(
            update(IngestJob)
            .where(IngestJob.id == job_id)
            .values(stage=stage, percent=percent, error_code=None, error_detail=None)
        )
        self.db.commit()

    def set_percent(self, job_id: int, percent: int) -> None:
        self.db.execute(update(IngestJob).where(IngestJob.id == job_id).values(percent=percent))
        self.db.commit()

    def fail(self, job_id: int, code: str, detail: str = "") -> None:
        """失败一律停在当前阶段，不自动重试 —— 等用户决定（PRD F3.2.5）。

        stage 有意**不改动**：重试时要从这里续跑，已完成阶段的产物复用。
        """
        job = self.db.get(IngestJob, job_id)
        if job is None:
            return
        self.db.execute(
            update(IngestJob)
            .where(IngestJob.id == job_id)
            .values(error_code=code, error_detail=detail[:2000], locked_at=None)
        )
        self.db.execute(update(Media).where(Media.id == job.media_id).values(status="failed"))
        self.db.commit()

    def finish(self, job_id: int) -> None:
        self.db.execute(
            update(IngestJob)
            .where(IngestJob.id == job_id)
            .values(stage="ready", percent=100, locked_at=None, error_code=None, error_detail=None)
        )
        self.db.commit()

    def retry_from_failed_stage(self, job_id: int) -> IngestJob | None:
        """清掉错误标记，让 worker 从记录的阶段续跑，已完成阶段的产物复用。"""
        job = self.db.get(IngestJob, job_id)
        if job is None:
            return None
        self.db.execute(
            update(IngestJob)
            .where(IngestJob.id == job_id)
            .values(error_code=None, error_detail=None, locked_at=None)
        )
        self.db.execute(update(Media).where(Media.id == job.media_id).values(status="processing"))
        self.db.commit()
        return self.db.get(IngestJob, job_id)
