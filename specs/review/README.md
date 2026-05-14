# Review Gate（人工审批闸门）

本目录用于控制工作流推进。

## 审批文件

### 1. requirement 审批
文件：
specs/review/{feature_id}.requirement.approved

作用：
表示需求已经澄清并确认，可以进入 02 设计阶段。

### 2. design 审批
文件：
specs/review/{feature_id}.design.approved

作用：
表示 PRD / 架构 / 测试设计已经人工确认，可以进入 03 构建阶段。

## 文件内容
任意非空文本即可，例如：

approved by Hui Shen
date: 2026-04-14

## 原则
AI 负责生成草稿  
人负责关键决策与审批
