"""worker 入口。轮询 ingest_jobs，跑四阶段管线。

只有一个进程在跑（单用户自托管），但出队仍走 claim_next 的加锁路径 ——
worker 崩溃重启后要能把半途的任务捡回来，靠的是 locked_at 超时回收。
"""

from __future__ import annotations

import logging
import signal
import sys
from types import FrameType

from sqlalchemy.orm import sessionmaker

from de_nachhall.config import LLMConfigError, get_settings, require_llm_credentials
from de_nachhall.db.session import create_db_engine
from de_nachhall.ingest.runner import JobRunner
from de_nachhall.ingest.stages import build_stages

log = logging.getLogger(__name__)

_stopping = False


def _stop(signum: int, frame: FrameType | None) -> None:
    global _stopping
    log.info("收到信号 %s，跑完当前阶段后退出", signum)
    _stopping = True


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    settings = get_settings()
    # 启动即失败（SPEC §8.1）。只有 worker 调 LLM，所以这条检查在这里，
    # 不在 Settings 里 —— 放进去会把从不碰 LLM 的 api 一并卡死。
    try:
        require_llm_credentials(settings)
    except LLMConfigError as e:
        log.error("配置不完整：%s", e)
        raise SystemExit(2) from e

    engine = create_db_engine(settings.database_url)
    db = sessionmaker(bind=engine, expire_on_commit=False)()

    stages = build_stages(settings)
    log.info(
        "worker 就绪：whisper=%s/%s llm=%s media_root=%s",
        settings.whisper_model, settings.whisper_device,
        settings.llm_provider, settings.media_root,
    )

    runner = JobRunner(db, stages)
    try:
        runner.loop(settings.worker_poll_interval_s, stop=lambda: _stopping)
    finally:
        db.close()
    log.info("worker 已退出")


if __name__ == "__main__":
    main()
