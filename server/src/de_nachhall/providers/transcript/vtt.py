"""WebVTT 解析。

平台字幕的 cue 按**显示行**断，不按语义句断 —— 一句话常被拆成 2–4 个 cue
（Sprint 0 实测：175 cue → 118 句）。这里只负责忠实解析，合并交给
chunking.sentences。
"""

from __future__ import annotations

import re

from de_nachhall.providers.transcript.base import FragmentOut

_CUE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*"
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})[^\n]*\n(.*?)(?=\n\s*\n|\Z)",
    re.S,
)
_TAG = re.compile(r"<[^>]+>")
# WebVTT 的定位/样式指令行，不是台词
_CUE_SETTING = re.compile(r"^(?:NOTE|STYLE|REGION)\b", re.I)


def _ms(h: str, m: str, s: str, f: str) -> int:
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(f)


def parse_vtt(text: str) -> list[FragmentOut]:
    out: list[FragmentOut] = []
    for match in _CUE.finditer(text):
        h1, m1, s1, f1, h2, m2, s2, f2, body = match.groups()
        lines = [
            ln.strip()
            for ln in body.splitlines()
            if ln.strip() and not _CUE_SETTING.match(ln.strip())
        ]
        clean = _TAG.sub("", " ".join(lines)).strip()
        # 说话人标记 "- " 在广播字幕里很常见，保留内容去掉前缀
        clean = re.sub(r"^-\s+", "", clean)
        if not clean:
            continue
        start, end = _ms(h1, m1, s1, f1), _ms(h2, m2, s2, f2)
        if end <= start:
            continue
        out.append(FragmentOut(idx=len(out), start_ms=start, end_ms=end, text=clean))
    return out
