# Changelog

## Unreleased

### 变更
- **移除 TickFlow 数据源**：CI workflow 的 `TICKFLOW_*` 环境变量、`.env.example` / `.claude.example.json` 配置项、CLI / TUI / 桌面端的 TickFlow Key 配置入口，以及文档中的 TickFlow 数据源描述与推广链接全部清除；行情统一走 Tushare，未配置或权限不足时依次降级到 AkShare / Baostock / efinance / 腾讯 / 新浪。数据质量合同阈值（OHLCV/市值 ≥95%、财务 ≥90%、`date_keyed_native_pct_v1`）不受影响。

### 改进
- **星球会员硬切与权限解耦**：Web、Worker、TUI 和数据库统一使用 `planet_members` 语义；会员身份不再代替个人数据源（Tushare 等）或模型配置，单股分析只在真实行情 Key 就绪后开放；前后端到期日统一按 `Asia/Shanghai` 自然日判断。
- **DeepSeek V4 全链路适配**：官方 Flash/Pro 统一支持 1M 上下文、`off/low/high/max` 思考强度和 Responses 联网搜索；旧 `deepseek-chat` / `deepseek-reasoner` 配置在官方端点按原思考语义迁移，代理端点保持普通兼容协议。网页专项报告、读盘室、后台任务、TUI 与桌面打包使用各自明确的完整输出策略。

### 修复
- **读盘室发布就绪校验**：生产 Worker 强制使用独立工具审批签名密钥，健康检查和部署流程会在密钥缺失或强度不足时直接失败，不再等到用户发起对话后才暴露配置错误。
- **TUI 模型故障切换**：本地和云端的 `deepseek` 配置统一识别为专用官方 provider；备用配置不可用时不再覆盖默认模型的原始错误，状态栏同步显示实际活跃模型。

## 0.9.3 (2026-05-19)

### 改进
- **记忆系统精简**: 只提取 `[偏好]` 和 `[决策]`，移除 `[股票]`/`[市场]` 等噪声类型
- **语义去重**: 新记忆保存时用 LLM 判断是否与已有记忆重复，避免同义反复
- **Ctrl+C 即时中断**: 流式等待从 60s 改为 0.5s 粒度轮询，按下即断
- **断联友好提示**: 网络异常不再静默卡死，显示中文错误信息
- **`/changelog` 命令**: 查看版本更新日志
