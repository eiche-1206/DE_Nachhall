"""订阅源。MVP 只读 —— 订阅管理不在本期范围（PRD §4）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from de_nachhall.db.models import Source, Subscription
from de_nachhall.deps import current_user_id, get_db
from de_nachhall.schemas.errors import ERROR_RESPONSES
from de_nachhall.schemas.media import SourceOut, SourcesResponse

router = APIRouter(prefix="/api/sources", tags=["sources"], responses=ERROR_RESPONSES)


@router.get("", response_model=SourcesResponse, summary="我订阅的源")
def list_sources(
    db: Annotated[Session, Depends(get_db)],
    uid: Annotated[int, Depends(current_user_id)],
) -> SourcesResponse:
    rows = db.scalars(
        select(Source)
        .join(Subscription, Subscription.source_id == Source.id)
        .where(Subscription.user_id == uid)
        .order_by(Source.id)
    ).all()
    return SourcesResponse(items=[SourceOut.model_validate(s) for s in rows])
