# Release Playbook

## 发布流程

### 1. 本地验证
- run_local_intake.sh 必须通过
- run_local_ci.sh 必须通过
- pytest 全部通过

### 2. 提交代码
- 提交到 main 分支
- 或通过 PR 合并

### 3. 自动流程（GitHub Actions）

#### 阶段 01
- 生成产品决策（brainstorm / scoring / decision / intake）

#### 阶段 02
- 生成 PRD / architecture / test-plan / test-cases

#### 阶段 03
- 自动生成代码 + 单元测试

#### 阶段 04
- 自动执行 pytest

#### 阶段 05
- 若失败 → 自动修复

#### 阶段 06
- 发布到 staging / production

## 环境说明

### staging
- 用于测试验证
- 可以自动部署

### production
- 必须人工审批
- 使用 production secrets

## 发布条件（必须满足）

- 所有测试通过
- 无高危安全问题
- 无硬编码密钥
- API 可正常访问

## 回滚策略

- 使用上一版本 tag 回滚
- 或重新部署上一个成功构建

## 注意事项

- 不允许跳过测试直接发布
- 不允许手动改线上数据
