"""ORM 的可移植性与约束测试。

重点测三件在 SQLite 上最容易出问题、且出问题时静默的事：
  1. BigInteger 主键在 SQLite 上能否自增
  2. 外键级联是否真的生效（SQLite 默认不强制外键）
  3. 唯一约束是否真的挡住重复
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from de_nachhall.db.models import (
    Base,
    Chapter,
    Chunk,
    Fragment,
    IngestJob,
    Media,
    Sentence,
    Source,
)
from de_nachhall.db.session import create_db_engine


@pytest.fixture()
def db(tmp_path) -> Session:  # type: ignore[no-untyped-def]
    engine = create_db_engine(f"sqlite+pysqlite:///{tmp_path/'t.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    yield s
    s.close()


def _media(db: Session, url: str = "https://example.test/a") -> Media:
    m = Media(source_url=url, origin="user", title="T", status="queued")
    db.add(m)
    db.commit()
    return m


class TestPortability:
    def test_bigint_pk_autoincrements_on_sqlite(self, db: Session) -> None:
        # BigInteger 主键在 SQLite 上不会自增，必须 with_variant(Integer)
        a, b = _media(db, "u1"), _media(db, "u2")
        assert a.id is not None and b.id is not None
        assert b.id > a.id

    def test_wal_and_foreign_keys_enabled(self, db: Session) -> None:
        from sqlalchemy import text

        assert db.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert db.execute(text("PRAGMA foreign_keys")).scalar() == 1


class TestConstraints:
    def test_source_url_is_unique(self, db: Session) -> None:
        _media(db, "same")
        with pytest.raises(IntegrityError):
            _media(db, "same")

    def test_media_status_check(self, db: Session) -> None:
        db.add(Media(source_url="x", origin="user", title="T", status="bogus"))
        with pytest.raises(IntegrityError):
            db.commit()

    def test_source_kind_check(self, db: Session) -> None:
        db.add(Source(name="s", kind="bogus"))
        with pytest.raises(IntegrityError):
            db.commit()

    def test_chunk_idx_unique_per_media(self, db: Session) -> None:
        m = _media(db)
        ch = Chapter(
            media_id=m.id, idx=0, start_sentence_idx=0, end_sentence_idx=1, start_ms=0, end_ms=1
        )
        db.add(ch)
        db.commit()
        for _ in range(2):
            db.add(
                Chunk(
                    media_id=m.id,
                    chapter_id=ch.id,
                    idx=0,
                    start_sentence_idx=0,
                    end_sentence_idx=1,
                    start_ms=0,
                    end_ms=1,
                    text="t",
                    word_count=1,
                )
            )
        with pytest.raises(IntegrityError):
            db.commit()


class TestCascade:
    def test_deleting_media_removes_all_derived_rows(self, db: Session) -> None:
        m = _media(db)
        ch = Chapter(
            media_id=m.id, idx=0, start_sentence_idx=0, end_sentence_idx=0, start_ms=0, end_ms=1
        )
        db.add_all(
            [
                ch,
                IngestJob(media_id=m.id, stage="queued"),
                Fragment(media_id=m.id, idx=0, start_ms=0, end_ms=1, text="f"),
                Sentence(media_id=m.id, idx=0, start_ms=0, end_ms=1, text="s", word_count=1),
            ]
        )
        db.commit()
        db.add(
            Chunk(
                media_id=m.id,
                chapter_id=ch.id,
                idx=0,
                start_sentence_idx=0,
                end_sentence_idx=0,
                start_ms=0,
                end_ms=1,
                text="c",
                word_count=1,
            )
        )
        db.commit()

        db.delete(m)
        db.commit()

        for model in (Chapter, Chunk, Fragment, Sentence, IngestJob):
            assert db.execute(select(model)).scalars().all() == []

    def test_deleting_source_keeps_media(self, db: Session) -> None:
        # 删源不该删掉已下载好的素材 —— SET NULL 而非 CASCADE
        src = Source(name="logo!", kind="official")
        db.add(src)
        db.commit()
        m = Media(source_id=src.id, source_url="u", origin="official", title="T")
        db.add(m)
        db.commit()

        db.delete(src)
        db.commit()
        db.refresh(m)
        assert m.id is not None
        assert m.source_id is None


class TestDefaults:
    def test_media_defaults(self, db: Session) -> None:
        m = _media(db)
        assert m.media_type == "video"
        assert m.status == "queued"
        assert m.created_at is not None

    def test_job_defaults(self, db: Session) -> None:
        m = _media(db)
        j = IngestJob(media_id=m.id)
        db.add(j)
        db.commit()
        assert (j.stage, j.percent, j.attempt, j.locked_at) == ("queued", 0, 0, None)
