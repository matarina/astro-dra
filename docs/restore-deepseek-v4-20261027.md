# 5002恢复原deepseek-v4-flash（2026-10-27）

> 文档定位：恢复事件；当前模型以current-status为准。本页记录当时过程；当前状态见[状态总览](current-status.md)，有效后续见[待办](roadmap.md)。

用户要求切回原模型，已将5002默认由原生deepseek/deepseek-flash恢复为openai_endpoint/deepseek-v4-flash，并恢复此前实际使用的OpenAI兼容地址和对应凭据。原配置从Azure切换前的私有备份`azure-gpt56-20261026-101806/.env.test-5002`取回；不是在官方DeepSeek接口上仅改模型名。

私有env只改模型、提供方、OpenAI兼容地址与对应密钥四项；Compose校验确认其余配置相同，部署后全部配置环境与实际容器一致。当前Azure地址/凭据已随本轮变更前env备份，可恢复；官方DeepSeek配置仍保留。密钥不写文档或公开JSON。

切换前在当前安装环境中临时覆盖候选连接，7项后端集成检查全部通过3.191秒：默认模型/原生provider、中文生成、流式、工具调用及回传、相关性、原生一致性与引用写作。没有创建完整研究任务。部署后不传模型覆盖，实际默认模型中文生成再验证通过；不是研究质量或长请求稳定性验收。

只重建5002应用，不重新构建/替换镜像：仍`astro-dra:generic-sources-20261026`。应用容器`a89770db55ec3a14393ddb1a29937d4dbeff0f2e812236d22d32259b97202135`，北京时间2026-10-27 10:05:42启动；healthy、登录HTTP200、新启动日志ERROR/CRITICAL计数0。原数据/配置卷保留，5000、SearXNG、relay的容器ID和启动时间未变。日志/trace未见新研究任务，最近真实任务已完成。

原生检查开、保存前QC关、来源500、PubMed自动全文默认关、私有trace开均保持。上轮未通过的数量提示试验仍未部署，研究/写作代码不改。新建任务默认使用恢复后的模型；旧页面若保留显式DeepSeek官方提供方选项，请刷新或选择openai_endpoint/deepseek-v4-flash。已保存报告不重写。

本轮私有备份`/data/ningh/nh/ldr-test-5002-backups/restore-deepseek-v4-20261027-100419/`；私有测试证据`/data/ningh/nh/ldr-experiments/restore-deepseek-v4-20261027/`。恢复本轮前默认时使用其中env，只重建5002应用并保留卷。Git fetch仍因认证不可用失败，无提交推送合并。
