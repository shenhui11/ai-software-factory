# AGENTS.md

## 项目约束（Project Contract）

本仓库采用严格路径控制（strict path policy）。

---

## 一、设计阶段输出（Design Phase）

你只允许写入以下文件：

- specs/prd/{feature_id}.md
- specs/architecture/{feature_id}.md
- specs/test-plan/{feature_id}.md
- specs/scoring/{feature_id}.json
- specs/decision/{feature_id}.md
- specs/brainstorm/{feature_id}.md
- specs/intake/{feature_id}.md
- specs/tests/{feature_id}.md
- specs/test-cases/{feature_id}.yaml

---

## 二、构建阶段输出（Build Phase）

你只允许修改：

- apps/**
- packages/**
- tests/**
- docs/**
- pyproject.toml
- requirements.txt
- requirements-dev.txt
- Makefile

---

## 三、自动修复阶段规则（Auto-fix rules）
- Auto-fix must only repair the minimum necessary scope for failing verification.
- Never bypass tests by deleting, skipping, or weakening them.
- Never disable lint, test, or verify workflows.


## 四、禁止行为（Forbidden）

禁止创建 repository-root directories：

- prd
- architecture
- test-plan
- test-cases

禁止：
- 在 specs/ 之外写设计文档
- 重构项目目录结构
- 创建替代路径

---

## 五、技术约束（Stack Rules）

- Backend 必须使用 FastAPI
- 测试必须使用 pytest
- 不允许使用 unittest 作为主测试框架
- 不允许硬编码 secrets / token / 数据库密码

---

## 六、行为规则（Behavior）

- 必须先读取 specs 和 docs，再进行实现
- 如果路径冲突，必须停止并报错
- 优先做最小变更（minimal change）
- 不允许“为了跑通”而更换技术方案
