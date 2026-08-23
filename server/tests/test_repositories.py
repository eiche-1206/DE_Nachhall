"""仓储层测试。重点是出队的正确性与时间线的 UNION 语义。"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from de_nachhall.db.models import Base, Media, Source, Subscription, User
from de_nachhall.db.session import create_db_engine
from de_nachhall.repositories.jobs import LOCK_TIMEOUT, JobsRepository
from de_nachhall.repositories.media import MediaRepository

UID = 1


@pytest.fixture()
def db(tmp_path):  # type: ignore[no-untyped-def]
    engine = create_db_engine(f"sqlite+pysqlite:///{tmp_path/'t.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    # 必须分步 flush：Subscription 没有 ORM relationship，SQLAlchemy 推不出
    # 插入顺序，可能先插关联表再插主表，撞上 FOREIGN KEY constraint failed
    s.add_all([User(id=UID, name="me"), Source(id=1, name="logo!", kind="official")])
    s.flush()
    s.add(Subscription(user_id=UID, source_id=1))
    s.commit()
    yield s
    s.close()


def mk(db: Session, url: str, *, source_id: int | None = 1, day: int = 1, **kw) -> Media:  # type: ignore[no-untyped-def]
    m = Media(
        source_url=url,
        source_id=source_id,
        origin="official" if source_id else "user",
        title=url,
        published_on=date(2026, 8, day),
        **kw,
    )
    db.add(m)
    db.commit()
    return m


class TestDedup:
    def test_find_by_url(self, db: Session) -> None:
        m = mk(db, "https://a")
        assert MediaRepository(db).find_by_url("https://a").id == m.id
        assert MediaRepository(db).find_by_url("https://nope") is None


class TestTimeline:
    def test_unions_subscribed_and_imported(self, db: Session) -> None:
        repo = MediaRepository(db)
        mk(db, "sub", source_id=1, day=1)
        own = mk(db, "own", source_id=None, day=2)
        repo.link_user_import(UID, own.id)
        assert {m.source_url for m in repo.timeline(UID)} == {"sub", "own"}

    def test_excludes_unrelated_media(self, db: Session) -> None:
        # 别人导入的、且不属于我订阅源的素材，不该出现在我的时间线
        mk(db, "orphan", source_id=None, day=3)
        assert MediaRepository(db).timeline(UID) == []

    def test_sorted_by_date_desc(self, db: Session) -> None:
        for d in (1, 3, 2):
            mk(db, f"u{d}", day=d)
        got = [m.published_on.day for m in MediaRepository(db).timeline(UID)]
        assert got == [3, 2, 1]

    def test_null_date_sorts_last(self, db: Session) -> None:
        mk(db, "dated", day=5)
        m = Media(source_url="undated", source_id=1, origin="official", title="x")
        db.add(m)
        db.commit()
        assert [x.source_url for x in MediaRepository(db).timeline(UID)] == ["dated", "undated"]

    def test_link_user_import_is_idempotent(self, db: Session) -> None:
        repo = MediaRepository(db)
        m = mk(db, "own", source_id=None)
        repo.link_user_import(UID, m.id)
        repo.link_user_import(UID, m.id)
        assert len(repo.timeline(UID)) == 1


class TestClaim:
    def test_claims_and_locks(self, db: Session) -> None:
        jobs = JobsRepository(db)
        m = mk(db, "a")
        jobs.enqueue(m.id)
        j = jobs.claim_next()
        assert j is not None and j.locked_at is not None and j.attempt == 1

    def test_locked_job_not_claimed_again(self, db: Session) -> None:
        jobs = JobsRepository(db)
        jobs.enqueue(mk(db, "a").id)
        assert jobs.claim_next() is not None
        assert jobs.claim_next() is None

    def test_stale_lock_is_reclaimed(self, db: Session) -> None:
        # worker 崩溃后任务必须能被重新捡起
        jobs = JobsRepository(db)
        job = jobs.enqueue(mk(db, "a").id)
        claimed = jobs.claim_next()
        assert claimed is not None
        claimed.locked_at = datetime.now(UTC) - LOCK_TIMEOUT - timedelta(minutes=1)
        db.commit()
        again = jobs.claim_next()
        assert again is not None and again.id == job.id and again.attempt == 2

    def test_finished_job_not_claimed(self, db: Session) -> None:
        jobs = JobsRepository(db)
        job = jobs.enqueue(mk(db, "a").id)
        jobs.finish(job.id)
        assert jobs.claim_next() is None

    def test_fifo_order(self, db: Session) -> None:
        jobs = JobsRepository(db)
        first = jobs.enqueue(mk(db, "a").id)
        jobs.enqueue(mk(db, "b").id)
        assert jobs.claim_next().id == first.id

    def test_empty_queue(self, db: Session) -> None:
        assert JobsRepository(db).claim_next() is None


class TestStageTransitions:
    def test_set_stage_clears_previous_error(self, db: Session) -> None:
        jobs = JobsRepository(db)
        job = jobs.enqueue(mk(db, "a").id)
        jobs.fail(job.id, "BOOM", "detail")
        jobs.set_stage(job.id, "downloading", 10)
        db.refresh(job)
        assert job.error_code is None and job.stage == "downloading"

    def test_fail_marks_media_and_releases_lock(self, db: Session) -> None:
        jobs = JobsRepository(db)
        m = mk(db, "a")
        job = jobs.enqueue(m.id)
        jobs.claim_next()
        jobs.fail(job.id, "DOWNLOAD_FAILED", "网络不可达")
        db.refresh(job)
        db.refresh(m)
        assert job.error_code == "DOWNLOAD_FAILED"
        assert job.locked_at is None  # 释放锁，允许重试
        assert m.status == "failed"

    def test_retry_resumes_from_recorded_stage(self, db: Session) -> None:
        jobs = JobsRepository(db)
        m = mk(db, "a")
        job = jobs.enqueue(m.id)
        jobs.set_stage(job.id, "transcribing", 40)
        jobs.fail(job.id, "TRANSCRIBE_FAILED")
        jobs.retry_from_failed_stage(job.id)
        db.refresh(job)
        db.refresh(m)
        # 阶段保留 —— 已完成的下载与转码不重跑
        assert job.stage == "transcribing"
        assert job.error_code is None
        assert m.status == "processing"
        assert jobs.claim_next() is not None
