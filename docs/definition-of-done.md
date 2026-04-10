# Definition of Done

一个功能被认为完成，必须满足：

## 功能层
- 所有 PRD 中的 acceptance criteria 被实现
- API 能正常调用

## 代码层
- 代码结构符合 architecture 文档
- 无明显重复代码

## 测试层
- 使用 pytest
- 每个核心功能有测试覆盖
- 测试可以一键运行通过

## 运行层
- 新环境可以安装依赖并运行
- 提供启动命令

## 安全层
- 不允许硬编码 token / 密码

## 文档层
- 提供运行说明
