"""四层文本的落库。fragments / sentences / chapters / chunks。

全部是「整体替换」语义，不做增量合并 —— 重跑转写或改 target 重切时，
旧数据必须整块消失。增量合并在这里只会制造对不齐的 idx。

replace_chapters_and_chunks 必须一起做：chunk 的 chapter_id 依赖章节，
分两次写会出现前端读到「有 chunk 但没有 chapter」的中间态。
"""

from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from de_nachhall.chunking.chunker import Chunk as ChunkOut
from de_nachhall.chunking.sentences import Sentence as SentenceOut
from de_nachhall.db.models import Chapter, Chunk, Fragment, Sentence
from de_nachhall.providers.enrich.base import ChapterOut
from de_nachhall.providers.transcript.base import FragmentOut


class TextRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------- fragments ----------

    def replace_fragments(self, media_id: int, fragments: list[FragmentOut]) -> None:
        self.db.execute(delete(Fragment).where(Fragment.media_id == media_id))
        self.db.add_all(
            Fragment(
                media_id=media_id, idx=f.idx, start_ms=f.start_ms, end_ms=f.end_ms, text=f.text
            )
            for f in fragments
        )
        self.db.commit()

    def load_fragments(self, media_id: int) -> list[Fragment]:
        return list(
            self.db.scalars(
                select(Fragment).where(Fragment.media_id == media_id).order_by(Fragment.idx)
            )
        )

    # ---------- sentences ----------

    def replace_sentences(self, media_id: int, sentences: list[SentenceOut]) -> None:
        self.db.execute(delete(Sentence).where(Sentence.media_id == media_id))
        self.db.add_all(
            Sentence(
                media_id=media_id,
                idx=s.idx,
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                text=s.text,
                word_count=s.word_count,
            )
            for s in sentences
        )
        self.db.commit()

    def load_sentences(self, media_id: int) -> list[SentenceOut]:
        """返回 chunking 层的 Sentence，便于直接喂给 build_chunks。"""
        rows = self.db.scalars(
            select(Sentence).where(Sentence.media_id == media_id).order_by(Sentence.idx)
        )
        return [
            SentenceOut(
                idx=r.idx,
                start_ms=r.start_ms,
                end_ms=r.end_ms,
                text=r.text,
                word_count=r.word_count,
            )
            for r in rows
        ]

    def apply_translations(self, media_id: int, translations: dict[int, str]) -> int:
        if not translations:
            return 0
        known = {
            r for r in self.db.scalars(select(Sentence.idx).where(Sentence.media_id == media_id))
        }
        n = 0
        for idx, zh in translations.items():
            if idx not in known:
                continue  # 模型偶尔会编出不存在的 idx，静默丢弃
            self.db.execute(
                update(Sentence)
                .where(Sentence.media_id == media_id, Sentence.idx == idx)
                .values(translation_zh=zh)
            )
            n += 1
        self.db.commit()
        return n

    # ---------- chapters + chunks ----------

    def replace_chapters_and_chunks(
        self,
        media_id: int,
        chapters: list[ChapterOut],
        chunks: list[ChunkOut],
        sentences: list[SentenceOut],
    ) -> None:
        by_idx = {s.idx: s for s in sentences}

        def span(a: int, b: int) -> tuple[int, int]:
            inside = [by_idx[i] for i in range(a, b + 1) if i in by_idx]
            if not inside:
                return 0, 0
            return inside[0].start_ms, inside[-1].end_ms

        # chunks 通过 FK ondelete=CASCADE 跟着章节走，但 SQLite 需显式先删
        self.db.execute(delete(Chunk).where(Chunk.media_id == media_id))
        self.db.execute(delete(Chapter).where(Chapter.media_id == media_id))
        self.db.flush()

        id_of: dict[int, int] = {}
        for ch in sorted(chapters, key=lambda c: c.idx):
            start_ms, end_ms = span(ch.start_sentence_idx, ch.end_sentence_idx)
            row = Chapter(
                media_id=media_id,
                idx=ch.idx,
                title=ch.title,
                start_sentence_idx=ch.start_sentence_idx,
                end_sentence_idx=ch.end_sentence_idx,
                start_ms=start_ms,
                end_ms=end_ms,
            )
            self.db.add(row)
            self.db.flush()  # 拿到自增 id 才能填 chunk.chapter_id
            id_of[ch.idx] = row.id

        for c in chunks:
            chapter_id = id_of.get(c.chapter_idx)
            if chapter_id is None:
                continue  # 章节被丢弃时对应 chunk 也不该存在
            self.db.add(
                Chunk(
                    media_id=media_id,
                    chapter_id=chapter_id,
                    idx=c.idx,
                    start_sentence_idx=c.start_sentence_idx,
                    end_sentence_idx=c.end_sentence_idx,
                    start_ms=c.start_ms,
                    end_ms=c.end_ms,
                    text=c.text,
                    word_count=c.word_count,
                )
            )
        self.db.commit()
