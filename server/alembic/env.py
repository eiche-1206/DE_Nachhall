"""Alembic 环境。URL 一律从 Settings 取，不在 ini 里硬编码。"""

from __future__ import annotations

from alembic import context
from sqlalchemy import pool

from de_nachhall.config import get_settings
from de_nachhall.db.models import Base
from de_nachhall.db.session import create_db_engine

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        # SQLite 不支持多数 ALTER，批处理模式用「建新表+拷贝」绕过
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_db_engine()
    with engine.connect() as conn:
        context.configure(
            connection=conn,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
