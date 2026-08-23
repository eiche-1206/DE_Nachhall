"""测试夹具。

VTT 解析在这里是**测试局部**的实现 —— 生产代码的解析器归
providers/transcript/vtt.py（TASK-011）。这里刻意重写一份，
避免 chunking 的测试依赖 providers 层。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from de_nachhall.chunking.sentences import Fragment

FIXTURES = Path(__file__).parent / "fixtures"

_CUE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})\n(.*?)(?=\n\n|\Z)",
    re.S,
)
_TAG = re.compile(r"<[^>]+>")


def parse_vtt(path: Path) -> list[Fragment]:
    raw = path.read_text(encoding="utf-8")
    out: list[Fragment] = []
    for m in _CUE.finditer(raw):
        h1, m1, s1, f1, h2, m2, s2, f2, text = m.groups()
        start = ((int(h1) * 60 + int(m1)) * 60 + int(s1)) * 1000 + int(f1)
        end = ((int(h2) * 60 + int(m2)) * 60 + int(s2)) * 1000 + int(f2)
        clean = _TAG.sub("", text).replace("\n", " ").strip()
        if clean:
            out.append(Fragment(idx=len(out), start_ms=start, end_ms=end, text=clean))
    return out


@pytest.fixture(scope="session")
def logo_fragments() -> list[Fragment]:
    """logo! 2026-08-21 的官方德语字幕，491 秒，Sprint 0 实测样本。"""
    return parse_vtt(FIXTURES / "logo_20260821.vtt")
