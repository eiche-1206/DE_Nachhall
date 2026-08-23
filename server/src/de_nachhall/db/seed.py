"""种子数据。幂等 —— 重复执行不产生重复行。

MVP 预置：
  users(1)              唯一用户，鉴权推 v2
  sources(logo!)        官方源，指向 logo.de
  subscriptions(1, 1)   默认订阅

素材源指向 **logo.de 而非 YouTube** —— Sprint 0 实测 YouTube 频道
0/4 有字幕，ZDF 官方站 4/4 有官方德语 VTT。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from de_nachhall.db.models import Source, Subscription, User

DEFAULT_USER_ID = 1
LOGO_SOURCE_NAME = "logo!"
LOGO_CHANNEL_URL = "https://www.logo.de/"


def seed(db: Session) -> None:
    user = db.get(User, DEFAULT_USER_ID)
    if user is None:
        user = User(id=DEFAULT_USER_ID, name="me")
        db.add(user)
        db.flush()

    src = db.execute(
        select(Source).where(Source.channel_url == LOGO_CHANNEL_URL)
    ).scalar_one_or_none()
    if src is None:
        src = Source(name=LOGO_SOURCE_NAME, kind="official", channel_url=LOGO_CHANNEL_URL)
        db.add(src)
        db.flush()

    exists = db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id, Subscription.source_id == src.id
        )
    ).scalar_one_or_none()
    if exists is None:
        db.add(Subscription(user_id=user.id, source_id=src.id))

    db.commit()
