"""引擎与会话。

SQLite 的两项设置不是可选的：
  WAL        —— 否则 worker 写阶段状态时会锁住整库，前端 2 秒轮询必然撞上
  busy_timeout —— 撞上时等待而不是立刻抛 "database is locked"
  foreign_keys —— SQLite 默认**不**强制外键，不开则 ON DELETE CASCADE 形同虚设
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from de_nachhall.config import get_settings

_BUSY_TIMEOUT_MS = 5000


def _tune_sqlite(dbapi_conn: Any, _record: Any) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


def create_db_engine(url: str | None = None) -> Engine:
    """显式传 url 时不读全局配置 —— 测试、迁移、一次性工具都走这条路。"""
    dsn = url if url is not None else get_settings().database_url
    is_sqlite = dsn.startswith("sqlite")

    engine = create_engine(
        dsn,
        future=True,
        # SQLite 跨线程：api 与 worker 是不同进程，但 FastAPI 内部有线程池
        connect_args={"check_same_thread": False} if is_sqlite else {},
    )
    if is_sqlite:
        event.listen(engine, "connect", _tune_sqlite)
    return engine


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_db_engine()
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    s = get_sessionmaker()()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
