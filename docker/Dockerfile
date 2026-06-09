FROM python:3.11-slim

# 安装系统依赖（mysql-client 用于 mysqladmin 命令）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    default-mysql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Node.js（用于前端构建）
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制项目文件
COPY . .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 构建前端
WORKDIR /app/frontend
RUN if [ -f package.json ]; then \
    npm install && \
    npm run build && \
    mkdir -p /app/src/web/static && \
    cp -r dist/* /app/src/web/static/; \
    fi

WORKDIR /app

# 暴露端口
EXPOSE 8080

# 启动命令
CMD ["python", "-m", "src.main", "--web"]
