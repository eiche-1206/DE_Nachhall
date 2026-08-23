"""downloading —— probe + 下载视频与封面。

probe 结果同时用于两件事：
  1. 立刻回填 media 的标题、时长、平台、发布日期（前端列表马上就有内容）
  2. 落盘给 transcribing 阶段选路用（平台字幕优先）

纯音频直接失败：回声闭环的第 1、3 步要播视频画面，没有画面产品形态不成立。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from de_nachhall.db.models import Media
from de_nachhall.ingest.runner import StageContext, StageError
from de_nachhall.ingest.workspace import Workspace
from de_nachhall.ingest.ytdlp import ProbeResult, Ytdlp, YtdlpError

log = logging.getLogger(__name__)


def _to_date(yyyymmdd: str | None) -> str | None:
    if not yyyymmdd or len(yyyymmdd) != 8 or not yyyymmdd.isdigit():
        return None
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"


class DownloadStage:
    def __init__(self, media_root: Path, ytdlp: Ytdlp) -> None:
        self.media_root = Path(media_root)
        self.ytdlp = ytdlp

    def __call__(self, ctx: StageContext) -> None:
        ws = Workspace.for_media(self.media_root, ctx.media.id)
        ws.ensure()

        # 重试续跑：source 还在（转封装没跑完）或 video.mp4 已经产出（source 被清掉了），
        # 都说明这一步上次已经做完，不重复拉一遍几百 MB
        existing = ws.source() or (ws.video if ws.video.exists() else None)
        if existing is not None and ws.probe_json.exists():
            log.info("media %s: reuse downloaded %s", ctx.media.id, existing.name)
            ctx.report(100)
            return

        ctx.report(5)
        try:
            probe = self.ytdlp.probe(ctx.media.source_url)
        except YtdlpError as e:
            raise StageError(e.code, e.message) from e

        if not probe.has_video:
            raise StageError(
                "AUDIO_NOT_SUPPORTED",
                "这是纯音频，暂时不支持。跟读需要画面配合。",
            )

        ws.write_probe(probe.raw)
        self._apply_metadata(ctx, probe)
        ctx.report(20)

        try:
            src = self.ytdlp.download(ctx.media.source_url, ws.root, basename="source")
        except YtdlpError as e:
            raise StageError(e.code, e.message) from e

        if src.stat().st_size == 0:
            raise StageError("DOWNLOAD_FAILED", "下载到的文件是空的，可重试。")

        ctx.report(90)
        self._fetch_thumb(ctx, ws)
        ctx.report(100)
        log.info("media %s downloaded: %s (%.1f MB)",
                 ctx.media.id, src.name, src.stat().st_size / 1e6)

    # ---------- 回填 ----------

    def _apply_metadata(self, ctx: StageContext, probe: ProbeResult) -> None:
        fields: dict[Any, Any] = {
            Media.platform: probe.platform,
            Media.duration_ms: probe.duration_ms,
        }
        # 标题只在还是占位（等于 URL）时才覆盖，用户改过的不动
        if ctx.media.title.strip() in ("", ctx.media.source_url):
            fields[Media.title] = probe.title
        if ctx.media.published_on is None:
            iso = _to_date(probe.upload_date)
            if iso:
                from datetime import date

                fields[Media.published_on] = date.fromisoformat(iso)

        ctx.db.query(Media).filter(Media.id == ctx.media.id).update(fields)
        ctx.db.commit()
        ctx.db.refresh(ctx.media)

    def _fetch_thumb(self, ctx: StageContext, ws: Workspace) -> None:
        """封面失败不影响主流程 —— 列表页缺张图不值得让整条素材失败。"""
        try:
            got = self.ytdlp.download_thumbnail(ctx.media.source_url, ws.root)
        except YtdlpError:
            got = None
        if got is None:
            return
        if got.name != ws.thumb.name:
            got.replace(ws.thumb)
        ctx.db.query(Media).filter(Media.id == ctx.media.id).update(
            {Media.thumb_path: ws.rel(ws.thumb)}
        )
        ctx.db.commit()
