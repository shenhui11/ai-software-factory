# Engineering Standards

## 基础规范
- 使用 Python 3.10+
- 后端必须使用 FastAPI
- 测试必须使用 pytest

## 项目结构
- apps/ 放应用代码
- tests/ 放测试
- specs/ 不允许修改（除非明确允许）

## 代码规范
- 函数必须有清晰命名
- 不允许超长函数（>100行）
- 不允许硬编码配置

## 依赖管理
- 使用 requirements.txt 或 pyproject.toml

## 错误处理
- API 必须有错误返回
- 不允许 silent fail

## 日志
- 核心流程必须有日志
