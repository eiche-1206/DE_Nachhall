"""素材的数据访问。

首页时间线是全站最核心的查询：订阅源的内容与自行导入的素材
**混排在一条时间线上**，不分 Tab（PRD A9）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session, selectinload

from de_nachhall.db.models import Chapter, Media, Subscription, UserMedia


class MediaRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------- 去重 ----------

    def find_by_url(self, source_url: str) -> Media | None:
        """全局去重的入口。同一 URL 只转写一次（SPEC A7）。"""
        return self.db.execute(
            select(Media).where(Media.source_url == source_url)
        ).scalar_one_or_none()

    # ---------- 时间线 ----------

    def _timeline_stmt(self, user_id: int) -> Select[tuple[Media]]:
        subscribed = select(Subscription.source_id).where(Subscription.user_id == user_id)
        imported = select(UserMedia.media_id).where(UserMedia.user_id == user_id)
        return (
            select(Media)
            .where(or_(Media.source_id.in_(subscribed), Media.id.in_(imported)))
            .order_by(Media.published_on.desc().nullslast(), Media.id.desc())
        )

    def timeline(self, user_id: int, *, limit: int = 200) -> list[Media]:
        stmt = (
            self._timeline_stmt(user_id)
            .options(selectinload(Media.job), selectinload(Media.chapters))
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def by_status(self, user_id: int, statuses: list[str]) -> list[Media]:
        stmt = (
            self._timeline_stmt(user_id)
            .where(Media.status.in_(statuses))
            .options(selectinload(Media.job))
        )
        return list(self.db.execute(stmt).scalars().all())

    # ---------- 详情 ----------

    def detail(self, media_id: int) -> Media | None:
        return self.db.execute(
            select(Media)
            .where(Media.id == media_id)
            .options(
                selectinload(Media.job),
                selectinload(Media.chapters).selectinload(Chapter.chunks),
            )
        ).scalar_one_or_none()

    # ---------- 写入 ----------

    def create(self, **kw: Any) -> Media:
        m = Media(**kw)
        self.db.add(m)
        self.db.commit()
        return m

    def link_user_import(self, user_id: int, media_id: int) -> None:
        exists = self.db.execute(
            select(UserMedia).where(UserMedia.user_id == user_id, UserMedia.media_id == media_id)
        ).scalar_one_or_none()
        if exists is None:
            self.db.add(UserMedia(user_id=user_id, media_id=media_id))
            self.db.commit()

    def set_status(self, media_id: int, status: str) -> None:
        m = self.db.get(Media, media_id)
        if m is not None:
            m.status = status
            self.db.commit()
