# FEAT-0001 Run Guide

## 安装

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## 启动

```bash
uvicorn apps.backend.main:app --host 0.0.0.0 --port 8000
```

```bash
cd apps/web
npm install
npm run build
```

## 测试

```bash
pytest -q
```
