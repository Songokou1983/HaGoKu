# HaGoKu Studio — API 后端 Docker 镜像
FROM python:3.11-slim

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 Python 依赖
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir -e .

# 复制应用代码
COPY hagoku/ ./hagoku/

# 运行时入口
EXPOSE 8000
CMD ["hagoku-api"]