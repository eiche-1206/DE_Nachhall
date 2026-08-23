# DE_Nachhall server —— 一份代码，两个 entrypoint
#
#   api    : 轻量，无 CUDA。跑 FastAPI。
#   worker : 基于 CUDA 运行时，跑六阶段 ingest 管线。
#
# 两者共享 src/，避免 schema 漂移（SPEC §2.2）。

# ============================================================
# api —— 不装 faster-whisper，省掉整套 CUDA 依赖
# ============================================================
FROM python:3.12-slim AS api

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# ffmpeg 与 yt-dlp：api 提交时要同步 probe（SPEC §5.3 probe-first）
RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
# 迁移脚本必须进镜像：初始化走的是 `docker compose run api python -m
# de_nachhall.initdb`，那条路只挂 src/，不挂整个 server/。漏了它的话
# 全新 clone 第一步就失败（实测过）。
COPY alembic.ini ./
COPY alembic ./alembic
RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["uvicorn", "de_nachhall.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--reload", "--reload-dir", "/app/src"]

# ============================================================
# worker —— CUDA 运行时 + cuDNN，faster-whisper 需要
# ============================================================
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 AS worker

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    HF_HOME=/models

# 基础镜像自带 Python 3.10，但项目要求 3.12 —— 用 deadsnakes 补上
RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends software-properties-common ca-certificates gnupg \
 && add-apt-repository -y ppa:deadsnakes/ppa \
 && apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends \
      python3.12 python3.12-venv python3.12-dev \
      ffmpeg curl \
 && rm -rf /var/lib/apt/lists/*

# 用 venv 而非系统 pip —— 基础镜像的 python3 是 3.10，不能混
RUN python3.12 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
RUN pip install --no-cache-dir -e ".[asr]"

CMD ["python", "-m", "de_nachhall.worker"]
