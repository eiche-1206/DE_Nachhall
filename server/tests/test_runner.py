"""JobRunner 测试。用假阶段，不碰网络、ffmpeg、GPU。

重点验三件在生产上最贵的行为：
  1. 失败停在**出错的那个阶段**，重试能从那里续跑
  2. transcribing 完成即 ready_partial —— 跟读不必等 enriching
  3. 阶段崩溃不会让轮询循环退出
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from de_nachhall.db.models import Base, Media
from de_nachhall.db.session import create_db_engine
from de_nachhall.ingest.runner import PIPELINE, JobRunner, StageContext, StageError
from de_nachhall.repositories.jobs import JobsRepository


@pytest.fixture()
def db(tmp_path):  # type: ignore[no-untyped-def]
    engine = create_db_engine(f"sqlite+pysqlite:///{tmp_path/'t.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    yield s
    s.close()


def make(db: Session) -> tuple[Media, object]:
    m = Media(source_url="https://x", origin="user", title="T")
    db.add(m)
    db.commit()
    return m, JobsRepository(db).enqueue(m.id)


def tracer(log: list[str], fail_at: str | None = None, crash_at: str | None = None):  # type: ignore[no-untyped-def]
    def make_stage(name: str):  # type: ignore[no-untyped-def]
        def stage(ctx: StageContext) -> None:
            log.append(name)
            if name == fail_at:
                raise StageError(f"{name.upper()}_FAILED", f"{name} 出错了")
            if name == crash_at:
                raise ValueError("未预期的崩溃")
            ctx.report(50)

        return stage

    return {n: make_stage(n) for n in PIPELINE}


class TestHappyPath:
    def test_runs_all_stages_in_order(self, db: Session) -> None:
        m, job = make(db)
        log: list[str] = []
        assert JobRunner(db, tracer(log)).run_job(job) is True
        assert log == list(PIPELINE)

    def test_ends_ready(self, db: Session) -> None:
        m, job = make(db)
        JobRunner(db, tracer([])).run_job(job)
        db.refresh(m)
        db.refresh(job)
        assert m.status == "ready"
        assert job.stage == "ready" and job.percent == 100

    def test_partial_ready_after_transcribing(self, db: Session) -> None:
        """跟读不必等 enriching —— 这是 PRD 明确要求的提前放行。"""
        m, job = make(db)
        seen: list[str] = []

        stages = tracer([])
        original = stages["enriching"]

        def spy(ctx: StageContext) -> None:
            db.refresh(m)
            seen.append(m.status)  # 进入 enriching 时 media 应已是 ready_partial
            original(ctx)

        stages["enriching"] = spy
        JobRunner(db, stages).run_job(job)
        assert seen == ["ready_partial"]


class TestFailure:
    def test_stops_at_failing_stage(self, db: Session) -> None:
        m, job = make(db)
        log: list[str] = []
        assert JobRunner(db, tracer(log, fail_at="transcribing")).run_job(job) is False
        assert log == ["downloading", "transcoding", "transcribing"]  # 不继续 enriching

    def test_records_stage_and_error(self, db: Session) -> None:
        m, job = make(db)
        JobRunner(db, tracer([], fail_at="transcribing")).run_job(job)
        db.refresh(job)
        db.refresh(m)
        assert job.stage == "transcribing"  # 停在出错的阶段
        assert job.error_code == "TRANSCRIBING_FAILED"
        assert "transcribing 出错了" in (job.error_detail or "")
        assert m.status == "failed"
        assert job.locked_at is None  # 释放锁，允许重试

    def test_unexpected_crash_is_caught(self, db: Session) -> None:
        m, job = make(db)
        assert JobRunner(db, tracer([], crash_at="transcoding")).run_job(job) is False
        db.refresh(job)
        assert job.error_code == "TRANSCODING_CRASHED"

    def test_missing_stage_registration(self, db: Session) -> None:
        m, job = make(db)
        assert JobRunner(db, {}).run_job(job) is False
        db.refresh(job)
        assert job.error_code == "STAGE_MISSING"


class TestRetry:
    def test_resumes_from_recorded_stage(self, db: Session) -> None:
        """已完成的下载与转码不重跑 —— 这是重试的全部价值。"""
        m, job = make(db)
        JobRunner(db, tracer([], fail_at="transcribing")).run_job(job)

        JobsRepository(db).retry_from_failed_stage(job.id)
        db.refresh(job)

        log: list[str] = []
        assert JobRunner(db, tracer(log)).run_job(job) is True
        assert log == ["transcribing", "enriching"]

    def test_full_rerun_when_failed_at_first_stage(self, db: Session) -> None:
        m, job = make(db)
        JobRunner(db, tracer([], fail_at="downloading")).run_job(job)
        JobsRepository(db).retry_from_failed_stage(job.id)
        db.refresh(job)
        log: list[str] = []
        JobRunner(db, tracer(log)).run_job(job)
        assert log == list(PIPELINE)


class TestTick:
    def test_returns_false_on_empty_queue(self, db: Session) -> None:
        assert JobRunner(db, tracer([])).tick() is False

    def test_processes_and_releases(self, db: Session) -> None:
        m, job = make(db)
        r = JobRunner(db, tracer([]))
        assert r.tick() is True
        db.refresh(job)
        assert job.locked_at is None and job.stage == "ready"

    def test_releases_lock_even_on_failure(self, db: Session) -> None:
        m, job = make(db)
        JobRunner(db, tracer([], fail_at="downloading")).tick()
        db.refresh(job)
        assert job.locked_at is None

    def test_progress_is_reported(self, db: Session) -> None:
        m, job = make(db)
        JobRunner(db, tracer([])).run_job(job)
        db.refresh(job)
        assert job.percent == 100
