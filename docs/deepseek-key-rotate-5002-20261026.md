# 5002 DeepSeek 密钥替换并加载（2026-10-26）

> 文档定位：历史操作摘要；凭据不在文档集合。本页记录当时过程；当前状态见[状态总览](current-status.md)，有效后续见[待办](roadmap.md)。

用户明确要求替换此前官方 DeepSeek 密钥，并在接入后重启。已替换 Git 忽略、0600 的 `.env.test-5002` 中 `LDR_LLM_DEEPSEEK_API_KEY`，没有把密钥写入源码或公开记录；此前新增的 Compose 原生 DeepSeek 环境映射本轮正式加载。

新密钥 `/v1/models` 返回 HTTP200，包含 `deepseek-flash`、`deepseek-v4-pro`；指定 `deepseek-flash` 的最小生成 HTTP200。模型连接继续使用原生 DeepSeek 提供方和 `https://api.deepseek.com/v1`。

只用现有镜像 force-recreate 5002 应用，没有构建镜像，没有变动5000、SearXNG、relay。部署前比较候选与实际环境，唯一差异为新增 DeepSeek 密钥。全局仍为 Azure `gpt-5.6-sol` / `openai_endpoint`；用户本轮要求替换备用连接密钥，没有要求切换默认模型。

5002 新容器 ID `bbb7da04d42c77e507d368eaf31c08ff42949b36024aac869d3259ee1924f39d`，北京时间10:59:16启动，healthy，登录页HTTP200。数据与配置卷保留，另三个服务ID和启动时间逐项未变。实际容器环境中的新密钥与私有配置一致。重启会结束旧进程内尚未完成的任务；本轮没有给旧任务伪造完成状态或修改账号数据库。

重启后在实际应用容器中执行现有后端兼容脚本，仅给测试进程指定 `deepseek` / `deepseek-flash`，没有持久改变全局默认。7项通过23.932秒：原生提供方/中文调用、流式、工具调用和回传、相关性、原生一致性及引用写作。新启动日志检查未见ERROR/CRITICAL。不是完整研究质量验收，上轮长等待/连接池问题本轮没有修复。

现在可刷新网页，在研究表单选择 `DeepSeek` 提供方与 `deepseek-flash` 模型进行测试。

备份：`/data/ningh/nh/ldr-test-5002-backups/deepseek-key-rotate-20261026-105830`；私有结果：`/data/ningh/nh/ldr-experiments/deepseek-key-rotate-20261026-105830`。脱敏状态见同名JSON。Git fetch仍认证失败，未提交、推送、合并。
