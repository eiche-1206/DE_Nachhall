"""视频流与缩略图。

**Range 不是优化，是前提**（SPEC §5.3、Sprint 0 V2b）。回声闭环每切一段
都要 `video.currentTime = X`；服务端不支持 Range 时浏览器只能从头下，
`seeked` 事件迟迟不来，整个闭环卡死。V2b 就是栽在这上面查了三层。

三种响应必须都对：
    无 Range        200 + Accept-Ranges: bytes
    有合法 Range    206 + Content-Range: bytes a-b/total
    越界            416 + Content-Range: bytes */total
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from de_nachhall.config import Settings
from de_nachhall.db.models import Media
from de_nachhall.deps import get_db, settings
from de_nachhall.schemas.errors import ERROR_RESPONSES, ApiError

router = APIRouter(prefix="/api/media", tags=["stream"], responses=ERROR_RESPONSES)

DB = Annotated[Session, Depends(get_db)]
CFG = Annotated[Settings, Depends(settings)]

_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
# 每次读 1 MB。太小则系统调用密集，太大则 seek 后要等一整块才出画面。
_CHUNK = 1024 * 1024


def _resolve(db: Session, cfg: Settings, media_id: int, attr: str, what: str) -> Path:
    m = db.get(Media, media_id)
    if m is None:
        raise ApiError(404, "NOT_FOUND", "找不到这条素材。")
    rel: str | None = getattr(m, attr)
    if not rel:
        raise ApiError(409, "NOT_READY", f"{what}还没准备好，等处理完成后再试。")

    root = Path(cfg.media_root).resolve()
    path = (root / rel).resolve()
    # 库里的相对路径理论上可信，但拼路径的地方一律做一次越界检查
    if not path.is_relative_to(root) or not path.is_file():
        raise ApiError(404, "FILE_MISSING", f"{what}文件不见了，重试这条素材可以重新生成。")
    return path


def _parse_range(header: str, size: int) -> tuple[int, int] | None:
    """返回闭区间 [start, end]，无法满足时返回 None（调用方回 416）。"""
    m = _RANGE.match(header.strip())
    if not m:
        return None
    first, last = m.group(1), m.group(2)
    if first:
        start = int(first)
        end = int(last) if last else size - 1
    elif last:
        # bytes=-500：最后 500 字节
        start, end = max(0, size - int(last)), size - 1
    else:
        return None
    end = min(end, size - 1)
    if start >= size or start > end:
        return None
    return start, end


def _read(path: Path, start: int, length: int) -> Iterator[bytes]:
    with path.open("rb") as f:
        f.seek(start)
        left = length
        while left > 0:
            block = f.read(min(_CHUNK, left))
            if not block:
                break
            left -= len(block)
            yield block


@router.get("/{media_id}/stream", summary="视频流（支持 Range）")
def stream(
    media_id: int,
    db: DB,
    cfg: CFG,
    request: Request,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
) -> Response:
    path = _resolve(db, cfg, media_id, "video_path", "视频")
    size = path.stat().st_size
    common = {
        "Accept-Ranges": "bytes",
        "Content-Type": "video/mp4",
        # 本地素材不会变，但 seek 依赖精确字节，宁可不缓存也不要拿到半旧的片段
        "Cache-Control": "no-store",
    }

    if range_header is None:
        return FileResponse(path, headers=common, media_type="video/mp4")

    rng = _parse_range(range_header, size)
    if rng is None:
        return Response(
            status_code=416,
            headers={**common, "Content-Range": f"bytes */{size}"},
        )

    start, end = rng
    length = end - start + 1
    return StreamingResponse(
        _read(path, start, length),
        status_code=206,
        headers={
            **common,
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(length),
        },
    )


@router.get("/{media_id}/thumb", summary="缩略图")
def thumb(media_id: int, db: DB, cfg: CFG) -> FileResponse:
    path = _resolve(db, cfg, media_id, "thumb_path", "封面")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})
