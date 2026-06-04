#!/usr/bin/env bash
# =============================================================================
# 企业级本体智能体 - macOS / Linux 启动脚本
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "╔══════════════════════════════════════════════════╗"
echo "║   企业级本体智能体 - 全栈服务启动               ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# 检查虚拟环境
if [ -d ".venv" ]; then
    VENV_DIR=".venv"
elif [ -d "venv" ]; then
    VENV_DIR="venv"
else
    echo "⚠ 未找到虚拟环境，正在创建..."
    python3 -m venv .venv
    VENV_DIR=".venv"
    echo "📦 安装依赖..."
    source "$VENV_DIR/bin/activate"
    pip install -r requirements.txt
fi

# 激活虚拟环境
source "$VENV_DIR/bin/activate"
echo "✅ 虚拟环境已激活: $VENV_DIR"

# 检查 .env
if [ ! -f ".env" ]; then
    echo "⚠ 未找到 .env，从模板复制..."
    cp .env.example .env
    echo "📝 请编辑 .env 填入实际配置"
fi

# 启动后端
echo ""
echo "[1/2] 启动后端 API 服务器 (端口 8888)..."
python -m ontology_intelligence.web.app &
BACKEND_PID=$!
echo "     后端 PID: $BACKEND_PID"

sleep 2

# 启动前端
echo "[2/2] 启动前端开发服务器 (端口 3000)..."
cd frontend
if [ ! -d "node_modules" ]; then
    echo "📦 安装前端依赖..."
    npm install
fi
npm run dev &
FRONTEND_PID=$!
echo "     前端 PID: $FRONTEND_PID"

cd "$PROJECT_ROOT"

echo ""
echo "═══════════════════════════════════════════════════"
echo "  所有服务已启动！"
echo ""
echo "  🌐 前端:   http://localhost:3000"
echo "  🔧 后端:   http://localhost:8888"
echo "  📊 Neo4j:  http://localhost:7474"
echo ""
echo "  按 Ctrl+C 停止所有服务"
echo "═══════════════════════════════════════════════════"

# 捕获退出信号
cleanup() {
    echo ""
    echo "🛑 正在停止服务..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    echo "✅ 服务已停止"
    exit 0
}
trap cleanup SIGINT SIGTERM

# 等待
wait
