"""六阶段管线调度。

关键设计（SPEC §2.5）：
  * 阶段状态每次变更都落库 —— 前端 2 秒轮询靠它显示进度
  * **失败一律停在当前阶段，不自动重试**（PRD F3.2.5）。用户决定是否重试，
    重试时从记录的阶段续跑，已完成阶段的产物复用
  * transcribing 完成即把 media.status 置为 ready_partial ——
    跟读此时已可用，不必等 enriching
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from de_nachhall.db.models import IngestJob, Media
from de_nachhall.repositories.jobs import JobsRepository

log = logging.getLogger(__name__)

# 顺序即执行顺序。重试时从 job.stage 所在位置继续。
PIPELINE: tuple[str, ...] = ("downloading", "transcoding", "transcribing", "enriching")

# 转写完成后素材即可跟读，不必等 enriching
PARTIAL_READY_AFTER = "transcribing"


class StageError(Exception):
    """阶段失败。code 进 ingest_jobs.error_code，message 面向用户。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class StageContext:
    db: Session
    media: Media
    job: IngestJob
    report: Callable[[int], None]


StageFn = Callable[[StageContext], None]


class JobRunner:
    def __init__(self, db: Session, stages: dict[str, StageFn]) -> None:
        self.db = db
        self.jobs = JobsRepository(db)
        self.stages = stages

    # ---------- 单个任务 ----------

    def run_job(self, job: IngestJob) -> bool:
        """跑完一个任务的剩余阶段。返回是否成功。"""
        media = self.db.get(Media, job.media_id)
        if media is None:
            self.jobs.fail(job.id, "MEDIA_MISSING", "素材记录已不存在。")
            return False

        start_at = self._resume_index(job.stage)
        self.db.query(Media).filter(Media.id == media.id).update({"status": "processing"})
        self.db.commit()

        for name in PIPELINE[start_at:]:
            fn = self.stages.get(name)
            if fn is None:
                self.jobs.fail(job.id, "STAGE_MISSING", f"阶段 {name} 未注册。")
                return False

            self.jobs.set_stage(job.id, name, 0)
            job_id = job.id

            def report(pct: int, _id: int = job_id) -> None:
                self.jobs.set_percent(_id, pct)

            ctx = StageContext(db=self.db, media=media, job=job, report=report)
            try:
                fn(ctx)
            except StageError as e:
                log.warning("stage %s failed for media %s: %s", name, media.id, e.message)
                self.jobs.fail(job.id, e.code, e.message)
                return False
            except Exception as e:  # noqa: BLE001
                log.exception("stage %s crashed for media %s", name, media.id)
                self.jobs.fail(job.id, f"{name.upper()}_CRASHED", str(e)[:500])
                return False

            self.jobs.set_percent(job.id, 100)
            if name == PARTIAL_READY_AFTER:
                # 跟读已可用，前端此时就能进回声闭环
                self.db.query(Media).filter(Media.id == media.id).update(
                    {"status": "ready_partial"}
                )
                self.db.commit()

        self.jobs.finish(job.id)
        self.db.query(Media).filter(Media.id == media.id).update({"status": "ready"})
        self.db.commit()
        log.info("media %s ready", media.id)
        return True

    @staticmethod
    def _resume_index(stage: str) -> int:
        """从记录的阶段续跑；queued 或未知值从头开始。"""
        try:
            return PIPELINE.index(stage)
        except ValueError:
            return 0

    # ---------- 轮询 ----------

    def tick(self) -> bool:
        """取一个任务跑完。无任务时返回 False。"""
        job = self.jobs.claim_next()
        if job is None:
            return False
        try:
            self.run_job(job)
        finally:
            self.jobs.release(job.id)
        return True

    def loop(self, interval_s: float, stop: Callable[[], bool] | None = None) -> None:
        while not (stop and stop()):
            try:
                if not self.tick():
                    time.sleep(interval_s)
            except Exception:  # noqa: BLE001 —— 循环不能因单次异常退出
                log.exception("runner tick failed")
                time.sleep(interval_s)
