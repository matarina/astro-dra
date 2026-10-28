# 5002 默认模型改为官方 DeepSeek Flash（2026-10-26）

用户明确要求把 `gpt-5.6-sol` 换成 `deepseek-flash`。已设置私有 `.env.test-5002` 的 `LDR_LLM_PROVIDER=deepseek`、`LDR_LLM_MODEL=deepseek-flash`，沿用上一轮替换并验证的官方密钥。原生 DeepSeek 提供方使用 `https://api.deepseek.com/v1`。Azure 连接保留作为可选提供方配置，不再是全局默认。

根 Compose 的提供方从固定 `openai_endpoint` 改为 `${LDR_LLM_PROVIDER:-openai_endpoint}`，示例环境新增原默认值，兼容原有部署。重建前比较实际与候选环境，差异只有模型和提供方；没有变动密钥、镜像、检索配置、来源容量和核查开关。

只用现有镜像重建5002应用，新容器 `0139142d67a6d1e84c705bba242ede73b227ff44ae622c8c78e6084b20e6b842`，北京时间11:06:13启动，healthy/登录HTTP200，新启动日志未见ERROR/CRITICAL。数据和配置卷保留；5000、SearXNG、relay容器ID和启动时间不变。

使用实际应用容器环境测试，未传任何模型/提供方覆盖。首次检查中文调用通过，随后固定字符串流式断言未通过；当时未捕获实际流式文本，不能判定是内容差异还是暂时异常。检查脚本仅补充失败时的短文本诊断，没有放宽断言或改应用处理。相同路径复查实际收到 `BACKEND_STREAM_OK`，全部7项通过13.005秒：原生提供方/中文、流式、工具调用与回传、相关性、原生一致性及引用写作；确认model=deepseek-flash、provider=deepseek、host=api.deepseek.com。保留首次失败与复查结果，不据此保证长期稳定性或整轮研究质量。

当前默认流程已使用 DeepSeek Flash；用户刷新网页后新建任务即可测试。如果表单仍保留旧任务显式选项，选择 DeepSeek / deepseek-flash。原生事实一致性开启、保存前逐引用QC关闭、来源500、PubMed自动全文关闭均未改。此前请求等待/数据库连接池问题本轮没有修复。

备份 `/data/ningh/nh/ldr-test-5002-backups/deepseek-default-20261026-110604`，私有结果 `/data/ningh/nh/ldr-experiments/deepseek-default-20261026-110604`，公开脱敏状态见同名JSON。Git fetch仍认证失败；未提交、推送、合并。
