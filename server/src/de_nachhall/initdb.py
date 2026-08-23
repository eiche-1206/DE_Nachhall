"""一次性初始化：建表 + 写入种子数据。

`docker compose up` 不会自己建表 —— 迁移是有副作用的操作，让它跟着容器
每次重启跑一遍，早晚会在某次意外重启时对着生产库执行到一半。所以初始化
是**显式的一条命令**：

    docker compose run --rm api python -m de_nachhall.initdb

两步都幂等，重复执行安全：
    alembic upgrade head   已经是最新版本时什么也不做
    seed()                 已存在的行不重复插
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.orm import sessionmaker

from de_nachhall.config import get_settings
from de_nachhall.db.seed import seed
from de_nachhall.db.session import create_db_engine

log = logging.getLogger(__name__)

# 镜像里 WORKDIR=/app，alembic.ini 与 alembic/ 都在那儿
_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s", stream=sys.stdout)
    settings = get_settings()

    if not _ALEMBIC_INI.exists():
        log.error("找不到 %s —— 请在 server/ 目录或 api 容器里运行这条命令。", _ALEMBIC_INI)
        raise SystemExit(2)

    log.info("建表：alembic upgrade head（%s）", settings.database_url)
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_ALEMBIC_INI.parent / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, "head")

    log.info("写入种子数据：用户、logo! 源、默认订阅")
    db = sessionmaker(bind=create_db_engine(settings.database_url))()
    try:
        seed(db)
    finally:
        db.close()

    log.info("初始化完成。现在可以 ./scripts/up.sh 了。")


if __name__ == "__main__":
    main()
