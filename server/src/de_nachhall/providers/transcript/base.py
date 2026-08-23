"""TranscriptProvider 协议。

入参是 MediaRef 而不是裸 wav 路径 —— 字幕类实现需要访问原始 URL 与
probe 信息。只给 wav 会把「平台字幕优先」这条路直接堵死。

选路策略（SPEC §4.2，Sprint 0 实测依据）：
    1. PlatformSubsProvider  —— probe 里有 de 且非自动生成的字幕轨
                                 ZDF 实测 4/4 命中，几秒完成，拼写 100% 正确
    2. FasterWhisperProvider —— 兜底。62 s / 8 分钟视频，词准确率 98.2%，
                                 但德语复合词会拆错（Dopingkontrolle → Doping Kontrolle）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class MediaRef:
    """转写的输入。同时携带音频与来源信息。"""

    media_id: int
    source_url: str
    wav_path: Path | None = None
    # yt-dlp extract_info 的原始结果，字幕类实现从这里找字幕轨
    probe: dict[str, Any] = field(default_factory=dict)

    @property
    def platform(self) -> str | None:
        key = self.probe.get("extractor_key") or self.probe.get("extractor")
        return str(key) if key else None


@dataclass(frozen=True)
class FragmentOut:
    idx: int
    start_ms: int
    end_ms: int
    text: str


class TranscribeError(RuntimeError):
    """转写失败。message 面向用户，须说明怎么修。"""


@runtime_checkable
class TranscriptProvider(Protocol):
    name: str

    def transcribe(self, media: MediaRef, lang: str) -> list[FragmentOut] | None:
        """返回 None 表示「这条路走不通，请回落下一个 Provider」。

        返回 None 与抛 TranscribeError 的区别很重要：
          None  —— 正常的不适用（如平台没有该语言字幕）
          抛错  —— 真的坏了（如显存不足），需要用户干预
        """
        ...
