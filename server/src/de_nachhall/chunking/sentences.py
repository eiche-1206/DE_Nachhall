"""fragment → sentence：按句末标点把碎片合并成完整句。

为什么需要这一步：
    平台字幕的 cue 按**显示行**断，不按语义句断。同一句话常被拆成
    2–4 个 cue（Sprint 0 实测：175 cue → 118 句）。直接拿 cue 当训练
    单元会让人跟读半句，语感全无。

这一层是纯函数，无 IO、无配置、无依赖 —— 便于用真实数据做回归测试。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 句末判定：终止标点后可跟收尾的引号或括号。
# 德语常用 » « „ " 以及英式引号，都要能收住。
_SENTENCE_END = re.compile(r'[.!?…]+["\'»«„”’)\]]*\s*$')

# 缩写与序数：句点不代表句末。德语文本里这几类最常见。
_NOT_END = re.compile(
    r"(?:^|\s)(?:"
    r"\d+\.|"  # 序数：21. August
    r"[A-ZÄÖÜ]\.|"  # 姓名首字母：J. Müller
    r"(?:bzw|ca|d\.h|evtl|ggf|inkl|Nr|Prof|Dr|St|Str|u\.a|usw|vgl|z\.B|zzgl)\."
    r")\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Fragment:
    idx: int
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class Sentence:
    idx: int
    start_ms: int
    end_ms: int
    text: str
    word_count: int


def _looks_like_sentence_end(text: str) -> bool:
    if not _SENTENCE_END.search(text):
        return False
    # 命中终止标点，但若结尾是缩写或序数则不算句末
    return not _NOT_END.search(text)


def merge_fragments_to_sentences(fragments: list[Fragment]) -> list[Sentence]:
    """把 fragment 按句末标点合并成完整句。

    末尾若残留未闭合的片段（说话被截断、字幕缺句号），照样成句 ——
    宁可多一个不规整的句子，也不能丢掉音频里真实存在的内容。
    """
    out: list[Sentence] = []
    buf_start: int | None = None
    buf_end = 0
    buf_parts: list[str] = []

    def flush() -> None:
        nonlocal buf_start, buf_end, buf_parts
        if buf_start is None:
            return
        text = " ".join(buf_parts).strip()
        if text:
            out.append(
                Sentence(
                    idx=len(out),
                    start_ms=buf_start,
                    end_ms=buf_end,
                    text=text,
                    word_count=len(text.split()),
                )
            )
        buf_start, buf_end, buf_parts = None, 0, []

    for frag in fragments:
        piece = frag.text.strip()
        if not piece:
            continue
        if buf_start is None:
            buf_start = frag.start_ms
        buf_end = frag.end_ms
        buf_parts.append(piece)

        if _looks_like_sentence_end(" ".join(buf_parts)):
            flush()

    flush()
    return out
