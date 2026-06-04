# AGENTS.md

本文件面向后续在本仓库中工作的编码 Agent。它不是用户手册，而是项目改动时的快速操作约定：先读现有结构，保持小范围修改，优先复用本仓库已有入口和模式。

## 项目概览

Ontology Intelligence 是企业级本体智能体项目，核心是把关系型数据通过本体映射同步到 Neo4j 知识图谱，并通过 LLM/Agent 提供自然语言查询、故障排查和可视化工作台。

主要技术栈：

- 后端：Python + FastAPI，入口在 `ontology_intelligence/web/app.py`，默认端口 `8888`。
- 前端：React + Vite，入口在 `frontend/src/main.jsx` 和 `frontend/src/App.jsx`，开发端口 `3000`。
- 图数据库：Neo4j，包含 n10s、向量索引、知识图谱查询。
- 关系型数据源：MySQL 为主，兼容 PostgreSQL / Oracle 的数据源配置。
- CDC/消息队列：Kafka + Debezium。
- 可观测性与提示词：Langfuse，相关逻辑在 Agent 和 Chat 路由中有容错降级。

## 关键目录

- `ontology_intelligence/`：Python 主包，包含配置、Agent、同步引擎、本体解析、FastAPI 路由和插件。
- `ontology_intelligence/config.py`：统一配置入口，优先使用其中的 `settings`，不要在新代码中散落读取环境变量。
- `ontology_intelligence/web/routes/`：后端 API 路由模块，所有路由由 `ontology_intelligence/web/app.py` 注册并统一挂到 `/api` 前缀。
- `ontology_intelligence/web/models.py`：通用 Pydantic 请求/响应模型；新增跨路由模型时优先放这里。
- `ontology_intelligence/sync/engine.py`：本体文件同步、MySQL 到 Neo4j 全量同步、映射加载和同步后校验入口。
- `ontology_intelligence/agent/core.py`：Neo4j Schema 提取、Cypher QA 工具、LangGraph Agent 和动态插件加载入口。
- `ontology_intelligence/agent/llm_factory.py`：LLM 与 Embedding 的统一工厂。
- `ontology_intelligence/plugins/`：当前插件目录。新增 Agent 工具插件时提供 `get_tool()`。
- `frontend/src/api.js`：前端 API 封装集中处，新增后端接口调用优先放这里。
- `frontend/src/pages/`：页面级 React 组件。
- `frontend/src/components/`：可复用组件和本体工作台等复杂组件。
- `docs/`：设计、运维、本体和集成文档。
- `scripts/`：部署和启动脚本。
- `database_mapping.yaml`：关系型数据到本体/Neo4j 的映射配置。
- `data/`、`ontology_workspace/`：运行时数据目录，通常不要作为代码改动提交。

## 常用命令

在项目根目录运行：

```bash
make install
make dev-backend
make dev-frontend
make build
make sync
make verify
python test_api.py
node test_browser.js
```

命令用途：

- `make install`：安装 Python 依赖，并进入 `frontend/` 安装前端依赖。
- `make dev-backend`：启动 FastAPI 后端，地址 `http://localhost:8888`。
- `make dev-frontend`：启动 Vite 前端，地址 `http://localhost:3000`。
- `make build`：构建前端生产包到 `frontend/dist/`。
- `make sync`：运行同步引擎，初始化 Neo4j、本体同步和关系型数据同步。
- `make verify`：校验 Neo4j 中的同步结果。
- `python test_api.py`：验证部分后端 API，要求后端已启动。
- `node test_browser.js`：用 Playwright 做基础前端可用性检查，要求前后端已启动。

## 后端约定

- 配置统一从 `ontology_intelligence.config.settings` 读取。路径解析优先用 `settings.project_root` 或已有配置属性。
- 新增 API 路由时，在 `ontology_intelligence/web/routes/` 下新增或扩展模块，并在 `ontology_intelligence/web/app.py` 中注册。
- 路由路径保持 `/api` 由 app 统一加前缀，单个 router 内不要重复写 `/api`。
- 需要鉴权的接口沿用 `verify_token` 依赖。
- 请求/响应结构优先使用 Pydantic 模型；跨多个路由复用的模型放到 `ontology_intelligence/web/models.py`。
- 长耗时同步任务使用现有线程池和状态模式，参考 `ontology_intelligence/web/routes/sync.py`。
- Chat/SSE 行为参考 `ontology_intelligence/web/routes/chat.py`，保持 `data: {...}\n\n` 的事件格式。
- Neo4j 查询和 Cypher 生成相关改动要注意安全拦截，避免让普通问答路径执行破坏性 Cypher。
- Langfuse 相关逻辑必须保持容错，不应让追踪或评分失败影响主业务响应。

## 前端约定

- 保持 `HashRouter` 路由模式，不要无故切换为 BrowserRouter。
- 新增页面放在 `frontend/src/pages/`，并在 `frontend/src/App.jsx` 注册路由。
- 通用 UI 或复杂功能组件放在 `frontend/src/components/`。
- 后端接口调用集中添加到 `frontend/src/api.js`，页面组件不要重复实现认证、401 处理和 JSON 错误处理。
- 使用现有 `useToast`、`useTheme`、`Layout` 等上下文与布局，不要平行新增一套全局状态模式。
- 上传文件时沿用 `FormData` 处理方式，让 `request()` 自动移除 `Content-Type`。
- 前端改动后至少运行 `cd frontend && npm run build`；涉及交互时再用 Playwright 或浏览器验证。

## 本体、同步与 Agent 约定

- 映射配置以 `database_mapping.yaml` 为根级默认文件，运行时路径来自 `settings.mapping_file`。
- `database_mapping.yaml` 中 `entity_class_strategy.type` 目前包含 `dynamic_column`、`static`、`relationship` 等策略，改动时同步考虑全量同步和可视化映射构建器。
- 同步引擎依赖 Neo4j、MySQL 和可选 Embedding 服务；无法连接外部服务时，不要把连接失败误判为纯代码问题。
- 本体文件支持 OWL/RDF/TTL/N3/NT/JSON-LD 等格式，相关解析在 `ontology_intelligence/ontology/parser.py` 和 Studio 路由中。
- Agent 工具插件应返回 LangChain `StructuredTool` 或可转换的工具对象，并暴露 `get_tool()`。
- 修改 `ontology_intelligence/agent/core.py` 时，重点保护：Schema 提取、Cypher 安全清理、Few-Shot 加载、Langfuse 降级、SQLite 会话记忆。
- 修改 Embedding 相关逻辑时，同步检查向量维度配置 `LLM_EMBEDDING_DIMENSIONS` 和 Neo4j 向量索引创建逻辑。

## 安全与数据注意事项

不要提交或在文档/代码中硬编码以下内容：

- `.env`
- `datasources.yaml`
- API Key、数据库密码、JWT Secret、Langfuse Secret
- `data/` 下的运行时数据、会话数据和本体工作台数据
- `ontology_workspace/`
- `*.db`、`*.db-shm`、`*.db-wal`、`*.sqlite3`
- `frontend/dist/`
- `node_modules/`、`.venv/`、`__pycache__/`

`.env.example` 只能作为变量名参考。新增示例配置时使用明显的占位值，不要使用真实内网地址、账号或密钥。

## 验证建议

- 文档或只读说明改动：人工复核 Markdown 即可。
- 后端纯逻辑改动：优先运行相关 Python 模块或最小 API 脚本；需要服务时先启动 `make dev-backend`。
- 前端改动：运行 `cd frontend && npm run build`。
- 前后端联动：启动后端和前端后，运行 `node test_browser.js` 或用浏览器检查对应页面。
- 同步/图谱改动：在外部服务可用时运行 `make sync` 和 `make verify`；如果依赖不可用，在交付说明中明确未运行原因。
- API 路由改动：确认前端 `frontend/src/api.js` 与后端路径、方法、请求体一致。

## 代码风格与协作

- 优先沿用现有模块边界和函数风格，避免为了单个需求引入大规模重构。
- 修改范围尽量贴近任务本身；不要整理无关文件、运行会重写大量文件的格式化命令，除非任务明确要求。
- 读写文件使用 UTF-8；中文文档保持中文，代码注释只在复杂逻辑处补充必要说明。
- 注意本仓库可能存在运行时生成文件。看到未跟踪或已修改的运行时数据时，不要主动清理或回滚。
- 涉及数据库写入、同步、删除本体、恢复版本等功能时，优先确认是否已有现成路由/工具可复用。
- 交付时说明实际验证过的命令；如果某些验证依赖本地服务而未运行，直接说明原因。
