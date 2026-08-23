"""FastAPI 依赖。

MVP 无认证，用户恒为 1（SPEC §1.1）—— 但**所有查询仍按 user_id 过滤**，
以后加认证时只需改这一个函数，不用回头翻每条 SQL。
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from de_nachhall.config import Settings, get_settings
from de_nachhall.db.session import get_sessionmaker

DEFAULT_USER_ID = 1


def get_db() -> Iterator[Session]:
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()


def current_user_id() -> int:
    return DEFAULT_USER_ID


def settings() -> Settings:
    return get_settings()
