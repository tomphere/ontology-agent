#!/usr/bin/env bash
# =============================================================================
# 企业级本体智能体 - Linux 服务器一键部署脚本
# =============================================================================
# 前置要求：Docker + Docker Compose
# 使用方法：bash scripts/deploy.sh
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# 0. 可选的自动更新
if [ "$1" == "--update" ] || [ "$2" == "--update" ]; then
    echo "🔄 检测到更新模式"
    if [ -d ".git" ]; then
        echo "⬇️ 正在从 Git 仓库拉取最新代码..."
        git pull origin master || echo "⚠ Git pull 失败,将使用当前代码重新构建"
    else
        echo "ℹ 当前目录不是 Git 仓库,跳过代码拉取"
        echo "   如需更新代码,请手动替换项目文件后重新运行此脚本"
    fi
fi

echo "╔══════════════════════════════════════════════════╗"
echo "║   企业级本体智能体 - 一键部署                   ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# 1. 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装。请先安装 Docker："
    echo "   curl -fsSL https://get.docker.com | bash"
    exit 1
fi
echo "✅ Docker 已安装: $(docker --version)"

if ! command -v docker compose &> /dev/null && ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose 未安装"
    exit 1
fi
echo "✅ Docker Compose 可用"

# 2. 检查 .env
if [ ! -f ".env" ]; then
    echo "⚠ 未找到 .env，从模板复制..."
    cp .env.example .env
    echo "📝 请编辑 .env 填入实际配置后重新运行:"
    echo "   nano .env"
    echo "   bash scripts/deploy.sh"
    exit 1
fi
echo "✅ .env 已存在"

# 3. 创建必要目录
mkdir -p data/chat_sessions ontology_workspace
echo "✅ 数据目录已创建"

# 4. 启动基础设施 (可选)
if [ "$1" == "--with-infra" ]; then
    echo ""
    echo "🔧 步骤 1/3: 启动附加基础设施 (Neo4j, Kafka, etc.)..."
    docker compose up -d
    echo "⏳ 等待基础设施就绪 (30s)..."
    sleep 30
else
    echo ""
    echo "⏭️ 步骤 1/3: 跳过基础设施启动 (直接使用服务器现有 Neo4j/Kafka)"
fi

# 5. 构建并启动应用
echo ""
echo "🔧 步骤 2/3: 构建并启动应用..."
docker compose -f docker-compose.app.yml up -d --build

# 6. 验证
echo ""
echo "🔧 步骤 3/3: 验证服务状态..."
sleep 5

BACKEND_OK=false
for i in {1..12}; do
    if curl -sf http://localhost:8888/api/auth/me > /dev/null 2>&1 || curl -sf http://localhost:8888/docs > /dev/null 2>&1; then
        BACKEND_OK=true
        break
    fi
    echo "  等待后端就绪... ($i/12)"
    sleep 5
done

if $BACKEND_OK; then
    echo "✅ 后端 API 已就绪"
else
    echo "⚠ 后端可能仍在启动中，请稍后检查"
fi

echo ""
echo "═══════════════════════════════════════════════════"
echo "  🎉 部署完成！"
echo ""
echo "  🌐 前端:   http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost'):3000"
echo "  🔧 后端:   http://localhost:8888"
echo "  📊 Neo4j:  http://localhost:7474"
echo ""
echo "  登录账号请使用 .env 中配置的 ADMIN_PASSWORD 或 ADMIN_PASSWORD_HASH"
echo ""
echo "  管理命令:"
echo "    查看日志: docker compose -f docker-compose.app.yml logs -f"
echo "    重启应用: docker compose -f docker-compose.app.yml restart"
echo "    停止所有: docker compose down && docker compose -f docker-compose.app.yml down"
echo "═══════════════════════════════════════════════════"
