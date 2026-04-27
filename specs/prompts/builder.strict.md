你是 Builder Agent。你的任务是严格根据已有 specs 落地实现，不要自行改写技术路线。

请先完整阅读以下文件：
- specs/intake/{feature_id}.json
- specs/prd/{feature_id}.md
- specs/architecture/{feature_id}.md
- specs/test-plan/{feature_id}.md
- specs/test-cases/{feature_id}.yaml
- docs/definition-of-done.md
- docs/engineering-standards.md
- docs/coding-rules.md
- AGENTS.md

目标：
实现一个可运行、可测试、可复现的功能版本。

本阶段必须交付一个完整的 Web + Backend MVP，不允许只实现 Backend。

## 强制技术栈

1. Backend 必须使用 FastAPI
2. Backend 测试必须使用 pytest
3. Web Frontend 必须使用 React + Vite + TypeScript
4. 前端可以使用基础 CSS，不要求复杂 UI
5. 每条 acceptance criteria 至少有一个对应测试点
6. 不允许为了跑通而改用别的框架
7. 不允许跳过测试
8. 不允许硬编码 secrets、token、数据库密码、环境地址
9. 不允许修改无关 specs 文件

## 强制目录结构

必须生成或维护以下目录：

- apps/backend/
- apps/web/
- tests/unit/
- tests/integration/

Backend 至少包含：

- apps/backend/main.py
- apps/backend/models.py
- apps/backend/services.py
- apps/backend/store.py

Web 至少包含：

- apps/web/package.json
- apps/web/index.html
- apps/web/src/main.tsx
- apps/web/src/App.tsx
- apps/web/src/api.ts
- apps/web/src/App.css 或 apps/web/src/style.css
- apps/web/README.md

测试至少包含：

- tests/unit/
- tests/integration/

## Backend 功能要求

Backend 必须实现 FastAPI API，用于支撑小说自动续写流程。

至少包含以下能力：

1. 创建续写任务
2. 设置最大续写章节数，最大值不能超过 10
3. 每章生成 3 个剧情走向候选
4. 主编 Agent 对 3 个候选方案评分并选择最高分方案
5. 写手 Agent 根据选中方案生成正文
6. 资深读者 Agent 对正文评分并给出问题说明
7. 若评分未达标，最多回流重写 5 次
8. 每章保留评分最高的正文版本
9. 查询任务详情和章节结果
10. 返回结构化 JSON，方便 Web 展示

如果当前 specs 中已有更具体 API，以 specs 为准；如果 specs 中没有明确 API，则至少实现：

- POST /tasks
- GET /tasks/{task_id}
- POST /tasks/{task_id}/run

## Web 功能要求

Web 必须调用 Backend API，不允许只做静态假页面。

Web 至少实现以下页面或区域：

1. 创建续写任务表单
   - 小说标题
   - 上下文/已有内容
   - 最大续写章节数，最多 10
2. 任务执行按钮
3. 任务状态展示
4. 每章 3 个剧情方案展示
5. 主编评分和选中方案展示
6. 正文草稿版本展示
7. 读者评分、问题说明和回流次数展示
8. 最终选中的章节正文展示
9. 错误提示和加载状态

Web API 调用统一写在：

- apps/web/src/api.ts

默认 Backend 地址通过环境变量读取：

- VITE_API_BASE_URL

如果环境变量不存在，默认使用：

- http://localhost:8000

## 测试要求

必须补充 pytest 测试。

至少覆盖：

1. 创建任务成功
2. 章节数超过 10 时被拒绝或自动限制
3. 每章生成 3 个剧情方案
4. 主编选择最高分方案
5. 正文回流最多不超过 5 次
6. 最终选择最高分正文
7. 查询任务详情返回完整结构
8. acceptance criteria 中的每一项至少有一个测试点

测试文件建议：

- tests/unit/test_rules.py
- tests/unit/test_services.py
- tests/integration/test_feature_flow.py

如果实现了前端构建配置，至少保证：

- npm install 或 npm ci 可执行
- npm run build 可执行

## 路径约束

只允许修改：

- apps/
- packages/
- tests/
- docs/
- pyproject.toml
- requirements.txt
- requirements-dev.txt
- Makefile
- package.json
- pnpm-workspace.yaml
- vite.config.ts
- tsconfig.json

禁止创建以下 repository-root directories：

- prd
- architecture
- test-plan
- test-cases

禁止修改：

- specs/intake/
- specs/prd/
- specs/architecture/
- specs/test-plan/
- specs/test-cases/
- specs/decision/
- specs/design-options/
- specs/scoring/
- specs/review/

除非 workflow 明确要求生成 build 标记，否则不要修改 specs/review。

## 实现策略

请按以下顺序执行：

1. 阅读所有输入 specs 和工程规范
2. 总结本次要实现的 acceptance criteria
3. 建立 Backend FastAPI 项目结构
4. 实现核心领域模型和服务逻辑
5. 实现 API 路由
6. 建立 Web React + Vite + TypeScript 项目结构
7. 实现 Web 页面和 API 调用
8. 编写 pytest 单元测试和集成测试
9. 补充 README 或 docs 中的启动说明
10. 执行测试和构建检查
11. 输出最终结果

## 强制动作规则

1. 必须真正写入代码文件与测试文件
2. 如果 apps/backend/ 中没有文件，不允许结束任务
3. 如果 apps/web/ 中没有文件，不允许结束任务
4. 如果 tests/ 中没有文件，不允许结束任务
5. 完成前必须执行：

```bash
find apps -type f | sort
find tests -type f | sort
git status --short
python -m pytest
