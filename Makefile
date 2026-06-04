# =============================================================================
# Ontology Intelligence - 跨平台开发命令
# =============================================================================

.PHONY: help install dev dev-backend dev-frontend build docker-up docker-app test sync verify

VENV_DIR ?= .venv
PYTHON ?= $(VENV_DIR)/bin/python
PIP ?= $(VENV_DIR)/bin/pip
SYSTEM_PYTHON ?= python3

$(PYTHON):
	@echo "🐍 未找到虚拟环境，正在创建 $(VENV_DIR)..."
	$(SYSTEM_PYTHON) -m venv $(VENV_DIR)
	$(PIP) install --upgrade pip

help: ## 显示帮助
	@echo "╔══════════════════════════════════════════════════╗"
	@echo "║   企业级本体智能体 - 开发命令                      ║"
	@echo "╚══════════════════════════════════════════════════╝"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@echo ""

install: $(PYTHON) ## 安装所有依赖
	@echo "📦 安装 Python 依赖..."
	$(PIP) install -r requirements.txt
	@echo "📦 安装前端依赖..."
	cd frontend && npm install
	@echo "✅ 所有依赖安装完成"

dev-backend: $(PYTHON) ## 启动后端开发服务器
	@echo "🚀 启动后端 (http://localhost:8888)..."
	$(PYTHON) -m ontology_intelligence.web.app

dev-frontend: ## 启动前端开发服务器
	@echo "🚀 启动前端 (http://localhost:3000)..."
	cd frontend && npm run dev

dev: ## 同时启动前后端（后台模式）
	@echo "🚀 启动全栈开发环境..."
	@make dev-backend &
	@sleep 2
	@make dev-frontend

build: ## 构建前端生产包
	@echo "📦 构建前端..."
	cd frontend && npm run build
	@echo "✅ 构建完成: frontend/dist/"

test: $(PYTHON) ## 运行后端单元测试
	@echo "🧪 运行后端测试..."
	$(PYTHON) -m pytest -q

sync: $(PYTHON) ## 运行同步引擎
	@echo "🔄 启动同步引擎..."
	$(PYTHON) -m ontology_intelligence.sync.engine

verify: $(PYTHON) ## 校验 Neo4j 数据
	@echo "🔍 运行数据校验..."
	$(PYTHON) -m ontology_intelligence.sync.verify

agent: $(PYTHON) ## 启动 CLI 智能体
	@echo "🤖 启动智能体..."
	$(PYTHON) -m ontology_intelligence.agent.core

docker-up: ## Docker 启动基础设施（Neo4j, Kafka等）
	docker compose up -d
	@echo "✅ 基础设施已启动"

docker-app: ## Docker 启动应用服务
	docker compose -f docker-compose.app.yml up -d --build
	@echo "✅ 应用服务已启动"

docker-down: ## Docker 停止所有服务
	docker compose down
	docker compose -f docker-compose.app.yml down 2>/dev/null || true
	@echo "✅ 所有服务已停止"

clean: ## 清理临时文件
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
	rm -rf frontend/dist 2>/dev/null || true
	@echo "✅ 清理完成"
