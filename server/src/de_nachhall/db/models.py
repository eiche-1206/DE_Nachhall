"""SQLAlchemy 2.0 ORM。表结构见 SPEC §3.3，评审结论见 §3.4。

可移植性约束 —— MVP 用 SQLite，以后可能换 Postgres，所以：
  * 主键用 BigInteger().with_variant(Integer, "sqlite")。
    SQLite 只有 INTEGER PRIMARY KEY 才走 rowid 自增，BIGINT 不会。
  * 时间统一 DateTime(timezone=True)，不写 TIMESTAMPTZ。
  * 部分索引同时给 sqlite_where 与 postgresql_where。
  * 不使用任何单一方言专有的 DDL。
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# SQLite 上退化为 INTEGER，才能自增；Postgres 上仍是 BIGINT
PK = BigInteger().with_variant(Integer, "sqlite")
FK = BigInteger().with_variant(Integer, "sqlite")

MEDIA_STATUS = ("queued", "processing", "ready_partial", "ready", "failed")
JOB_STAGE = ("queued", "downloading", "transcoding", "transcribing", "enriching", "ready", "failed")


class Base(DeclarativeBase):
    pass


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


# ==================== 用户与素材源 ====================


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (CheckConstraint("kind IN ('official','user')", name="ck_sources_kind"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    channel_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class Subscription(Base):
    __tablename__ = "subscriptions"

    user_id: Mapped[int] = mapped_column(
        FK, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[int] = mapped_column(
        FK, ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = _created_at()


# ==================== 素材 ====================


class Media(Base):
    __tablename__ = "media"
    __table_args__ = (
        CheckConstraint("origin IN ('official','user')", name="ck_media_origin"),
        CheckConstraint("media_type IN ('video','audio')", name="ck_media_type"),
        CheckConstraint(
            "status IN ('queued','processing','ready_partial','ready','failed')",
            name="ck_media_status",
        ),
        Index("idx_media_timeline", "published_on", "id"),
        Index("idx_media_status", "status"),
    )

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    # NULL = 用户自行导入，不属于任何订阅源
    source_id: Mapped[int | None] = mapped_column(FK, ForeignKey("sources.id", ondelete="SET NULL"))
    # 全局去重锚点：同一 URL 只转写一次
    source_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # yt-dlp 的 extractor_key：ZDF / Youtube / ARDMediathek …
    platform: Mapped[str | None] = mapped_column(String(64))
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    media_type: Mapped[str] = mapped_column(String(16), nullable=False, default="video")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    published_on: Mapped[date | None] = mapped_column(Date)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    video_path: Mapped[str | None] = mapped_column(Text)
    thumb_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    created_at: Mapped[datetime] = _created_at()

    job: Mapped[IngestJob | None] = relationship(
        back_populates="media", cascade="all, delete-orphan", uselist=False
    )
    chapters: Mapped[list[Chapter]] = relationship(
        back_populates="media", cascade="all, delete-orphan", order_by="Chapter.idx"
    )
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="media", cascade="all, delete-orphan", order_by="Chunk.idx"
    )


class UserMedia(Base):
    """仅记录**用户自行导入**的素材。订阅源的素材不写这里。"""

    __tablename__ = "user_media"

    user_id: Mapped[int] = mapped_column(
        FK, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    media_id: Mapped[int] = mapped_column(
        FK, ForeignKey("media.id", ondelete="CASCADE"), primary_key=True
    )
    imported_at: Mapped[datetime] = _created_at()


# ==================== 任务队列 ====================


class IngestJob(Base):
    """与 media 分表：media 是长期数据，这里是过程数据。

    高频 UPDATE（stage / percent / locked_at）落在独立表上，
    不会持续在 media 表制造死元组。
    """

    __tablename__ = "ingest_jobs"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('queued','downloading','transcoding','transcribing',"
            "'enriching','ready','failed')",
            name="ck_jobs_stage",
        ),
        Index("idx_jobs_pending", "stage", "locked_at"),
    )

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    media_id: Mapped[int] = mapped_column(
        FK, ForeignKey("media.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    stage: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_detail: Mapped[str | None] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 超时回收：worker 崩溃后任务能被重新捡起
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    media: Mapped[Media] = relationship(back_populates="job")


# ==================== 四层文本 ====================


class Fragment(Base):
    """平台字幕 cue 或 Whisper 碎片。保留它才能改 target 重切而不重跑转写。"""

    __tablename__ = "fragments"
    __table_args__ = (UniqueConstraint("media_id", "idx", name="uq_fragments_media_idx"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    media_id: Mapped[int] = mapped_column(
        FK, ForeignKey("media.id", ondelete="CASCADE"), nullable=False
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class Sentence(Base):
    """完整句。翻译挂在这一层 —— chunk 的翻译是其句子翻译的拼接。"""

    __tablename__ = "sentences"
    __table_args__ = (UniqueConstraint("media_id", "idx", name="uq_sentences_media_idx"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    media_id: Mapped[int] = mapped_column(
        FK, ForeignKey("media.id", ondelete="CASCADE"), nullable=False
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # NULL = enriching 未完成，或走了 NullEnricher 降级
    translation_zh: Mapped[str | None] = mapped_column(Text)


class Chapter(Base):
    """一条独立新闻。是 chunk 合并的**硬边界**，不可跨越。"""

    __tablename__ = "chapters"
    __table_args__ = (UniqueConstraint("media_id", "idx", name="uq_chapters_media_idx"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    media_id: Mapped[int] = mapped_column(
        FK, ForeignKey("media.id", ondelete="CASCADE"), nullable=False
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    # NULL = NullEnricher 降级，无标题
    title: Mapped[str | None] = mapped_column(Text)
    start_sentence_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    end_sentence_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    media: Mapped[Media] = relationship(back_populates="chapters")
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="chapter", cascade="all, delete-orphan", order_by="Chunk.idx"
    )


class Chunk(Base):
    """训练单元。

    text 是冗余字段（可从 sentences join 拼出），有意保留 ——
    回声页每次切段都读它，join 拼接在热路径上。
    代价：改 sentences.text 必须同步这里（SPEC §3.4 判断 ②）。
    """

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("media_id", "idx", name="uq_chunks_media_idx"),
        Index("idx_chunks_chapter", "chapter_id", "idx"),
    )

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    media_id: Mapped[int] = mapped_column(
        FK, ForeignKey("media.id", ondelete="CASCADE"), nullable=False
    )
    chapter_id: Mapped[int] = mapped_column(
        FK, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False
    )
    # 全期连续编号，前端显示 ¶11 / 53
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    start_sentence_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    end_sentence_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)

    media: Mapped[Media] = relationship(back_populates="chunks")
    chapter: Mapped[Chapter] = relationship(back_populates="chunks")
