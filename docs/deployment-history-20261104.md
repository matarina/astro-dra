# Docker 部署与迁移

2026-10-28当前行为：默认来源为PubMed、SearXNG、Europe PMC；候选12/筛后6、常规来源池500。事实检查开关控制最终writer后的证据核对和有限修订；`LDR_VERIFY_ENABLE_CITATION_QC=false`关闭的是另行保存前逐引用审计，二者不同。旧四项附表和强制发布门槛不走主报告路径。PubMed自动全文默认关，按需fetch保留；模型与端点由私有环境配置，表单允许按次选择。完整行为及限制见[累计变化](5002-vs-main-20261028.md)；下面带2026-10-16日期的实现描述属于历史阶段。


根目录的 `compose.yaml` 使用独立项目名 `astro-dra`，包含应用和 SearXNG。SearXNG 默认配置启用 HTML/JSON 搜索结果，只通过 Compose 内部网络提供服务；应用连接 `http://searxng:8080`，不依赖原机器的 8888 端口或代理。应用继承基础镜像的入口与健康检查，并在入口完成卷权限设置后切换到普通用户。

## 配置

复制根目录 `.env.example` 为 `.env`。填写 `LDR_LLM_OPENAI_ENDPOINT_URL`、`LDR_LLM_MODEL` 和模型凭据，生成随机 `SEARXNG_SECRET`。示例端点和模型名仅为占位，不能直接发起研究。根目录 `.env` 与旧部署目录内的 `.env` 分别管理，旧凭据不会自动迁入。

| 变量 | 默认行为 |
| --- | --- |
| `LDR_PORT` / `LDR_BIND_ADDRESS` | 宿主机 `127.0.0.1:5000` |
| `ASTRO_DRA_IMAGE` | 输出镜像 `astro-dra:local`；发布时用独立版本标签 |
| `LDR_BASE_IMAGE` | 已捕获的上游镜像 digest；更新时需审核补丁兼容性 |
| `LDR_LLM_LLAMACPP_URL` / `LDR_LLM_LLAMACPP_API_KEY` | 可选第二模型服务，独立于默认OpenAI endpoint；默认localhost:8080/v1，密钥可空 |
| `LDR_APP_ALLOW_REGISTRATIONS` | 初次启动允许创建账号，之后可关闭 |
| `LDR_VERIFY_ENABLE_VERIFY` | 独立核验模块总开关；不是报告准入门槛，关闭不代表核验通过 |
| `LDR_GENERAL_ENABLE_FACT_CHECKING` | 默认true；最终成文后核对引用与研究属性，可有限补证、确认和修订 |
| `LDR_VERIFY_ENABLE_CITATION_QC` | 默认false；单独的保存前逐引用语义审计 |
| `LDR_RESEARCH_TRACE_ENABLED` | 通用部署默认false；5002私有测试环境开启，过程存`/data/research_traces` |
| `LDR_SEARCH_SNIPPETS_ONLY` | 新部署默认false，允许获取摘要/内容；true时搜索片段不能证明论文原文支持 |
| `LDR_HTTP_PROXY` / `LDR_HTTPS_PROXY` | 默认http://host.docker.internal:9876，大小写变量保持一致 |
| `LDR_NO_PROXY` | 包含 Compose 服务和宿主别名，私有模型端点需另行加入 |
| `LDR_VERIFY_CROSSREF_MAILTO` | 建议替换为维护者联系邮箱 |

其他核验开关在 `VerifyConfig` 中定义，可通过本地 Compose 覆盖文件的 `environment` 添加。Compose 的 `.env` 用于变量插值，并非自动传入所有环境变量。额外搜索引擎密钥也需显式添加环境映射。

5002新增Qwen Flash时，将`LDR_LLM_LLAMACPP_URL`设为`http://27.30.76.162:6183/ai/v1`，并把该IP加入`LDR_NO_PROXY`。研究表单高级选项选择`llama.cpp`，刷新模型列表后选择包含`Qwen3.8-Flash-Next`的模型；必须保留服务返回的完整模型ID。模型/提供方允许按次选择，部署环境指定的默认值不被写回修改；重新加载页面恢复默认DeepSeek。模型地址与凭据仍由部署配置管理。此选择用于普通/详细研究，聊天模式沿用原有默认模型逻辑。

前端部署补丁为`local_deep_research/overlay/research.js`和`settings_sync.js`，取自当前固定基础镜像，通过manifest安装；旁置上游目录中的同名文件不参与部署。修改前端后执行`node --check`与`node scripts/check_model_selection.cjs`，构建新镜像。真实接口烟测可在应用容器内执行`scripts/check_qwen_flash.py`，覆盖模型发现、LDR客户端、中文回复、流式和工具往返，不等同于完整生物医学研究质量验收。

项目代理统一使用9876：应用通过大小写HTTP_PROXY/HTTPS_PROXY变量配置，SearXNG在deployment/searxng/settings.yml的outgoing.proxies中配置，两者均指向http://host.docker.internal:9876。SearXNG和应用均配置host-gateway解析。私有模型端点、localhost和searxng保留在NO_PROXY，避免模型或内部服务绕行代理。

若宿主机代理仅监听127.0.0.1:9876，在私有.env文件中加入COMPOSE_PROFILES=loopback-proxy；root Compose的proxy-relay服务以host网络运行，仅绑定Docker网关地址9876，转发到宿主127.0.0.1:9876。脚本deployment/proxy_relay.py只做TCP转发，不记录请求正文或凭据。同一宿主机只需启用一份转发服务，其他实例可复用该网关端口，不应重复绑定。宿主代理已监听Docker可访问地址时，无需启用此profile。

## 验证与远程访问

```bash
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=100 local-deep-research searxng
docker compose exec local-deep-research /install/.venv/bin/python -c 'import research_verify; print(research_verify.__version__)'
```

检查容器健康状态后，用真实模型配置完成一个短研究，核实检索、报告、引用、保存和导出。模块导入和健康检查不能证明模型或所有搜索引擎可用。

远程主机可通过 SSH 转发访问：`ssh -L 5000:127.0.0.1:5000 user@server`。需要直接公开服务时，明确配置监听地址，并由部署环境提供 HTTPS、反向代理与访问控制。

## 已有部署迁移与回滚

旧部署的 `local_deep_research/docker-compose.yml`、本地生产覆盖文件及数据保持原状。新入口不会自动复用它们的数据卷。若宿主机 5000 已被占用，先设置根目录 `.env` 中 `LDR_PORT=5001`，使用独立数据验收。

迁移前记录旧镜像 ID、实际 Compose 文件、卷名、配置和数据库备份。在没有活跃研究任务时进行最终备份与切换。只有确认数据兼容后，才通过本地覆盖文件将新服务的卷映射到实际旧卷；不同版本不要同时写同一数据库。

示例覆盖文件 `compose.migration.local.yml`（将卷名替换为实测名称）：

```yaml
volumes:
  ldr_data:
    external: true
    name: actual_old_data_volume
  ldr_config:
    external: true
    name: actual_old_config_volume
```

部署时显式指定 `docker compose -f compose.yaml -f compose.migration.local.yml up -d`。所有后续管理命令应使用同一组 Compose 文件。

发布前给已验证镜像设置独立标签，并记录镜像 ID。回滚时将 `ASTRO_DRA_IMAGE` 指回保留的旧版本，执行 `docker compose up -d --no-build`。数据库迁移兼容性需单独验证，恢复数据必须使用相应备份；不要用代码回滚代替数据库恢复。

`docker compose stop` 保留容器与数据。`docker compose down` 移除容器和项目网络，但保留命名卷；`down -v` 会删除项目数据卷，不应用于普通停止或回滚。

应用通用日志位于 `/data/logs/`，补丁另将用户名、任务 ID 和提问保存为 `user_questions.log`。这份明文日志由补丁独立写入，与通用文件日志开关分离；管理员需要按业务要求管理其访问和保留周期。

## 报告保存与辅助引用核查（2026-10-16最新方向）

普通/详细/定时报告保留生成内容，`publish_report`只处理引用链接及独立辅助审计。新`claim_publication`为schema 2.0、status unverified，核查明细在metadata，不追加正文，不依据判定删改或阻断报告。数据库/文件允许不带核验记录的普通调用；携带发布metadata时只检查内容、来源映射和序列化一致性。历史schema 1.0只读兼容；过期审计不能在展示时替换实际正文。

根Compose的自动与Agent来源仅保留PubMed、SearXNG，SearXNG仅Bing。私有账号快照仍由运行注册策略覆盖；用户动态Collection/Retriever及手动显式调用不在本次全局禁用范围。PubMed摘要/PMC正文获取与既有网页正文提取保留，不保证每篇全文可得。

代码需构建新镜像才生效；只改旁置上游源码不会部署。当前轮已构建astro-dra:advisory-20261016用于隔离验证，运行5002仍需核对实际镜像，不能根据工作区推断已部署。备份、模型/代理配置及旧实例数据隔离要求保持适用。完整流程见current-research-flow-20261016.md。
