# GitHub 发布前检查清单

本项目曾在本地运行过，发布到 GitHub 前必须使用无历史、无运行时数据的干净副本。不要直接推送当前 `.git` 历史。

## 必做步骤

1. 轮换所有曾经出现在本地配置中的密钥、密码和 API key。
2. 从干净导出目录重新初始化 git，不复用当前仓库 `.git` 目录。
3. 确认以下文件和目录没有进入新仓库：
   - `.env`、`.env.*`
   - `datasources.yaml`
   - `data/`
   - `ontology_workspace/`
   - `node_modules/`、`.venv/`
   - `frontend/dist/`
   - `*.db`、`*.sqlite3`、`*.db-wal`、`*.db-shm`
4. 发布前运行敏感信息扫描：

```bash
rg -n -i "(api[_-]?key|secret|password|passwd|pwd|token|authorization|bearer|jwt|private key|sk-|pk-|gpustack_|ark-|172\\.16\\.|/Users/)" .
```

5. 在干净导出目录中验证：

```bash
git status --ignored --short
python -m compileall -q ontology_intelligence tests
cd frontend && npm ci && npm run build
```

## 推荐发布流程

```bash
bash scripts/create_github_export.sh
cd ../ontology-agent-github-export
git init
git add .
git status --short
git commit -m "Initial public release"
git branch -M main
git remote add origin git@github.com:<owner>/<repo>.git
git push -u origin main
```

如果 `rg` 扫描仍命中真实密钥、内网地址、个人身份信息、业务人员信息或运行时数据，先停止发布并清理。
