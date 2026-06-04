# =============================================================================
# Ontology Intelligence - Docker 镜像构建
# =============================================================================
# 构建包含后端 API + 前端静态文件的单一镜像
# =============================================================================

FROM python:3.12-slim AS backend

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY ontology_intelligence/ ontology_intelligence/
COPY database_mapping.yaml .
COPY .env.example .env.example

# 创建数据目录
RUN mkdir -p data/chat_sessions data/scenes ontology_workspace

# 环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8888

CMD ["python", "-m", "ontology_intelligence.web.app"]

# =============================================================================
# 前端构建阶段
# =============================================================================
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --production=false 2>/dev/null || npm install
COPY frontend/ .
RUN npm run build

# =============================================================================
# Nginx 前端服务
# =============================================================================
FROM nginx:alpine AS frontend

COPY --from=frontend-build /app/frontend/dist /usr/share/nginx/html

# Nginx 反向代理配置
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
