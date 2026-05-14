# FEAT-0001 运行说明

## 安装

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## PostgreSQL 初始化

```bash
export PGHOST=192.168.21.109
export PGPORT=5432
export PGUSER=postgres
export PGPASSWORD='使用你提供的数据库密码'
export APP_DATABASE_URL='postgresql://postgres:使用你提供的数据库密码@192.168.21.109:5432/ai-software-factory'
bash apps/scripts/init-postgres.sh ai-software-factory
bash apps/scripts/postgres-smoke.sh ai-software-factory
```

如果希望显式拆分鉴权库连接，也可以额外设置：

```bash
export AUTH_DATABASE_URL="$APP_DATABASE_URL"
```

如果你改成本机测试环境，直接把主机切到 `127.0.0.1` 即可：

```bash
export PGHOST=127.0.0.1
export PGPORT=5432
export PGUSER=postgres
export PGPASSWORD='你的本地 PostgreSQL 密码'
export APP_DATABASE_URL='postgresql://postgres:你的本地 PostgreSQL 密码@127.0.0.1:5432/ai-software-factory'
bash apps/scripts/init-postgres.sh ai-software-factory
bash apps/scripts/postgres-smoke.sh ai-software-factory
```

你当前这台机器可直接使用的连接串格式如下：

```bash
export APP_DATABASE_URL='postgresql://postgres:Lanqian%402024@127.0.0.1:5432/ai-software-factory'
export AUTH_DATABASE_URL="$APP_DATABASE_URL"
```

为了避免把数据库密码提交进仓库，开发启动脚本支持从本地文件读取配置。推荐做法：

```bash
cp apps/scripts/.env.local.example apps/scripts/.env.local
```

然后把 `apps/scripts/.env.local` 改成你的真实连接串，例如：

```bash
APP_DATABASE_URL='postgresql://postgres:Lanqian%402024@127.0.0.1:5432/ai-software-factory'
AUTH_DATABASE_URL="$APP_DATABASE_URL"
CODEX_API_KEY='你的真实 API Key'
CODEX_BASE_URL='http://newapi.hjlyywp.com/v1'
CODEX_MODEL='gpt-5.4'
CODEX_TIMEOUT_SECONDS='240'
CODEX_RETRY_ATTEMPTS='2'
```

说明：
- 当前后端默认只使用 PostgreSQL。
- 只有在显式设置 `APP_STORAGE_BACKEND=sqlite` 或 `AUTH_STORAGE_BACKEND=sqlite` 时，才会启用 SQLite 兜底，主要用于测试或临时本地调试。

## 启动

```bash
uvicorn apps.backend.main:app --host 0.0.0.0 --port 8000
```

```bash
cd apps/web
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

如果使用一键开发启动脚本，它会优先读取 `apps/scripts/.env.local`；未配置 `APP_DATABASE_URL` / `AUTH_DATABASE_URL` 时会直接报错并停止启动。AI 相关配置也建议写进这个文件，不要只依赖当前 shell 的临时 `export`：

```bash
bash apps/scripts/restart-dev.sh
```

如果通过局域网或端口映射访问页面，例如 `http://47.101.217.218:62721/`，后端仍保持监听在宿主机 `0.0.0.0:8000` 即可。当前开发模式推荐不配置 `VITE_API_BASE_URL`，让前端请求先进入 Vite，再由 Vite 将 `/api`、`/admin` 和 `/health` 代理到本机 `127.0.0.1:8000`。`apps/scripts/restart-dev.sh` 也会在启动前主动清理 `VITE_API_BASE_URL`，避免误走直连模式。

## 测试

```bash
pytest -q
```
