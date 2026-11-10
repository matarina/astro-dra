# 5002 新增官方 DeepSeek 连接配置（2026-10-26，未重启）

> 文档定位：当时仅准备；不表示当前默认或可用性。本页记录当时过程；当前状态见[状态总览](current-status.md)，有效后续见[待办](roadmap.md)。

用户要求新增 DeepSeek API，使用 `deepseek-flash`，本次不要重启。配置已准备完成，但未加载到正在运行的应用；5002 当前仍以 Azure `gpt-5.6-sol` 为默认模型。

## 配置

- 复用镜像内已有的原生 `DeepseekProvider`，走 OpenAI 兼容接口 `https://api.deepseek.com/v1`；无需新增 Anthropic 适配层。官方说明见[接入文档](https://api-docs.deepseek.com/quick_start/agent_integrations/)。
- `compose.yaml` 新增可选 `LDR_LLM_DEEPSEEK_API_KEY` 映射，`.env.example` 只添加空占位。用户提供的凭据只写入 Git 忽略的 `.env.test-5002`，权限 0600，不写入源码或公开文档。
- 未替换现有 Azure URL、凭据、全局模型或提供方，未改检索与检查开关。没有构建镜像或重建现有容器。
- 下次经用户授权重新创建应用容器时，才会加载新凭据；单纯 `docker restart` 不更新容器环境。加载后在研究表单选择提供方 `DeepSeek`、模型 `deepseek-flash`。本轮没有将 DeepSeek 设为全局默认，也没有改原生提供方类中历史的缺省模型；使用时明确选 `deepseek-flash`。

## 验证

官方 `/v1/models` 返回 HTTP 200，包含 `deepseek-flash`、`deepseek-v4-pro`；指定 `deepseek-flash` 的最小请求 HTTP 200，正确返回约定文本。最小请求显式关闭 thinking，仅用于快速鉴权验证；没有据此改变应用的 thinking 参数。

扩展现有 `scripts/check_openai_backend.py`，同时支持原生 DeepSeek 和自定义 OpenAI 端点，错误输出对环境中的 API key 脱敏。一次性容器使用当前应用镜像和网络，从 stdin 接收候选环境，明确指定 `deepseek` / `deepseek-flash`，不挂载用户数据卷。7 项检查全部通过，合计 12.952 秒：环境及原生提供方、中文回答、流式、工具调用、工具结果回传、相关性筛选、原生一致性检查及带引用写作。该路径未额外指定 thinking 参数，测试后容器已删除。这是小规模后端兼容性验证，不是整轮研究准确率评估。

配置语法、脚本 AST、相关文件 diff 检查通过。四个现有容器的 ID、镜像、启动时间逐项与备份相同；5002 healthy、登录页 HTTP 200，运行环境中仍没有新增 DeepSeek 凭据。5000、SearXNG、relay 均未重启。

备份：`/data/ningh/nh/ldr-test-5002-backups/deepseek-flash-stage-20261026-103017`。私有验证记录：`/data/ningh/nh/ldr-experiments/deepseek-flash-stage-20261026/`；脱敏结果见同名 JSON。Git fetch 仍因认证失败不可用；未提交、推送或合并。下一步等待用户决定何时加载新增连接，本次不执行重启。
