"""每条素材一个目录。阶段之间靠**文件**传递中间产物，不靠内存。

理由是重试：失败停在当前阶段，用户点重试时进程可能已经换了一个
（worker 重启、机器重开）。已完成阶段的产物必须能被后续阶段重新捡起来，
所以 probe 结果也落盘，而不是只存在 StageContext 里。

    {MEDIA_ROOT}/{media_id}/
        probe.json    yt-dlp extract_info 原始结果（下载阶段写，转写阶段读）
        source.*      yt-dlp 下载的原始文件，容器格式不确定
        video.mp4     重封装后的可 seek 文件 —— 前端播的是这个
        audio.wav     16k 单声道，喂 Whisper
        thumb.jpg     封面
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Workspace:
    root: Path

    @classmethod
    def for_media(cls, media_root: Path, media_id: int) -> Workspace:
        return cls(root=Path(media_root) / str(media_id))

    def ensure(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    # ---------- 固定产物 ----------

    @property
    def probe_json(self) -> Path:
        return self.root / "probe.json"

    @property
    def video(self) -> Path:
        return self.root / "video.mp4"

    @property
    def wav(self) -> Path:
        return self.root / "audio.wav"

    @property
    def thumb(self) -> Path:
        return self.root / "thumb.jpg"

    def source(self) -> Path | None:
        """yt-dlp 下载的原始文件，扩展名由平台决定。"""
        for p in sorted(self.root.glob("source.*")):
            if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".ts", ".m4v", ".mov"):
                return p
        return None

    # ---------- probe 读写 ----------

    def write_probe(self, info: dict[str, Any]) -> None:
        self.ensure()
        self.probe_json.write_text(
            json.dumps(info, ensure_ascii=False, default=str), encoding="utf-8"
        )

    def read_probe(self) -> dict[str, Any]:
        if not self.probe_json.exists():
            return {}
        try:
            data = json.loads(self.probe_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def rel(self, path: Path) -> str:
        """存进数据库的是相对 MEDIA_ROOT 的路径，换挂载点不用改库。"""
        return str(Path(self.root.name) / path.name)
