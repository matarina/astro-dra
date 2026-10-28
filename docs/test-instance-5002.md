最新版本（2026-10-27 14:43:06）：5002已部署astro-dra:evidence-flow-20261027（72de350f…），healthy/登录200、10模块SHA匹配、默认真实生成及实际ldruser模拟流程通过。新增通用必要来源保留、明确版本补取/比较、写后分项核对和有限争议补证；语义漏检仍存在，不能视为全面解决。原接口deepseek-v4-flash及原卷、其他服务保持，用户刷新新建任务可测试。详见[本轮实现和限制](evidence-flow-20261027.md)。

2026-10-27 17:40最新：5002已部署astro-dra:review-repairs-20261027，默认仍deepseek-v4-flash/openai_endpoint。修复段落引文核对、独立web补证、未决跨轮保留、原子引句适配、表格及未声称属性协议、确认分析身份歧义，并增加有预算的PMC精确元数据身份桥；真实STAT3D重复书目回放合一。394回归及实际安装流程通过，双模型完整/聚焦对照和Flash新检索已保存；不同阶段代码范围及语义限制须看[本轮记录](review-repairs-model-comparison-20261027.md)和[报告索引](../reports/model-comparison-20261027.md)。完整新检索使用早期三项编排候选，并非最终全部补丁重跑；IF条件和模型漏判仍存在。原生开/QC关/自动全文默认关/来源500/trace开不变，5000和依赖容器未动。下方旧镜像描述为历史时点。


最新模型（2026-10-27 10:05:42）：5002已恢复原接口的deepseek-v4-flash/openai_endpoint并重启，a89770db…healthy/HTTP200，实际默认生成通过。镜像仍generic-sources，数据卷、其他服务及检索/核查/trace参数保持，数量提示试验未部署。见[恢复原模型](restore-deepseek-v4-20261027.md)。

最新状态（2026-10-26 17:46:29）：5002已部署astro-dra:generic-sources-20261026，healthy/HTTP200，13模块SHA匹配。修复富文本角色、同篇入口身份、正式通知关系携带与私有工具返回记录，不为[63]加入计数规则。343回归及实际安装镜像离线/模拟流程通过；当时默认deepseek-flash，原卷及其他服务保留。详见[通用来源修复](generic-source-repairs-20261026.md)。

最新版本（2026-10-26 15:11）：5002已部署astro-dra:synthesis-trace-20261026并重启，healthy/登录200；DeepSeek / deepseek-flash默认。新任务私有记录中间证据，原生检查加入问题及数据/计数/标题关联，仍写前检查且QC关闭，未增加模型调用。323回归及聚焦流程通过，原数据卷保留。见[记录与检查优化](synthesis-trace-20261026.md)。

最新模型状态（2026-10-26 10:23:04）：5002默认已暂时切换Azure gpt-5.6-sol并重启，openai_endpoint提供方；原镜像、数据卷、500来源及检查开关不变，healthy/HTTP200，原生流式/工具/写作集成验证通过。刷新网页后新建任务测试。详见[Azure部署与回退](azure-gpt56-deploy-5002-20261026.md)。下方DeepSeek默认为历史状态。

最新状态（2026-10-21 15:41:53）：5002已更新astro-dra:abstract-context-20261021，常规候选池500，完整摘要与分批材料选择、Europe PMC路由/正文获取已生效；原生检查开启、保存前逐引用审计关闭，DeepSeek默认不变。详见[本轮实现与验证](abstract-context-20261021.md)。下文镜像和容量为历史记录。

# 5002 开发测试实例

日期：2026-10-16。分支：work/ldr-20261012；构建时HEAD为bfb2e00，包含当前尚未提交的第6项代码。
访问：http://10.0.11.40:5002/ （服务器本机：http://127.0.0.1:5002/）。
独立数据为空，首次使用需在登录页注册新账号，原实例账号和研究记录不会自动迁入。

## 实际部署

- Compose项目：astro-dra-test-5002；根目录compose.yaml。
- 应用镜像：astro-dra:search-stability-20261016-v2。
- 镜像ID：sha256:fc50ef18b85cc5943cf5965be121dd36d1fe01e3fb14403a73a0a29731220bad。
- 映射：0.0.0.0:5002 -> 应用5000。
- 应用容器：astro-dra-test-5002-local-deep-research-1。
- SearXNG容器：astro-dra-test-5002-searxng-1，仅内部访问。
- 独立数据卷：astro-dra-test-5002_ldr_data、astro-dra-test-5002_ldr_config。
- 私有配置：仓库根.env.test-5002，权限0600，已被Git及Docker构建上下文忽略；不复制或提交该文件。
- 使用现有模型连接配置，模型deepseek-v4-flash；开启核验、关闭仅片段模式。
- 未修改5000/5001服务或数据；未合并main或推送GitHub。本轮fetch仍因认证不可用失败。

## 已验证

应用与SearXNG均healthy。根路径跳转/auth/login，登录和注册页面HTTP 200且含表单。
容器访问模型/models返回200，配置的模型在返回列表中。
11个覆盖文件和18个research_verify模块共29个文件的容器内SHA256与工作区一致。
检查应用数据/配置卷与5000、5001服务均不相同。

这只是启动与连接检查，不代表浏览器完整研究、端到端功能或第6项验收完成。
当前已知限制：最新真实生成验收普通报告0条、详细5条，整个M3-A第6项仍未完成；不得将此次启动视为问题已修复。

## 管理命令

在/data/ningh/nh/astro-dra目录运行，始终带相同项目名和配置文件：

查看状态：

    docker compose -p astro-dra-test-5002 --env-file .env.test-5002 -f compose.yaml ps

停止（保留数据）：

    docker compose -p astro-dra-test-5002 --env-file .env.test-5002 -f compose.yaml stop

再次启动：

    docker compose -p astro-dra-test-5002 --env-file .env.test-5002 -f compose.yaml up -d --no-build

修改代码后更新测试实例（先构建成功，再执行下一条）：

    docker compose -p astro-dra-test-5002 --env-file .env.test-5002 -f compose.yaml build local-deep-research
    docker compose -p astro-dra-test-5002 --env-file .env.test-5002 -f compose.yaml up -d --no-build

切换分支不会自动更新运行中的镜像。停止或删除容器不等于删除数据；不要使用down -v作普通停止。

## 代理修复（2026-10-16）

原配置继承了失效的host.docker.internal:2081。现应用HTTP_PROXY/HTTPS_PROXY及小写变量均使用http://host.docker.internal:9876；SearXNG的outgoing.proxies同步配置9876。
宿主sing-box仅监听127.0.0.1:9876，所以私有.env.test-5002启用COMPOSE_PROFILES=loopback-proxy；新增astro-dra-test-5002-proxy-relay-1，绑定Docker网关9876转发到宿主回环9876。上述启停命令会自动读取该profile，无需手动另开转发进程。
应用、SearXNG、relay均healthy，重建应用/SearXNG容器时保留数据卷；网页仍在5002。
经应用真实环境验证：Crossref HTTP200，默认SearXNG搜索HTTP200并返回10条，模型/models HTTP200且NO_PROXY直连。部分搜索引擎仍有timeout/CAPTCHA，不等于全部引擎可用。
arXiv经代理已能收到HTTP响应，但返回429；原ProxyError已消除，arXiv检索仍受上游限流，暂缓重复请求，不能宣称arXiv已恢复成功。
旧部署Compose中2081也已替换为9876供未来重建使用；本次只重建5002测试容器，未重启5000/5001服务，也未更改宿主sing-box的监听配置。

## 当前检索稳定性版本

限流来源已临时退出Agent/自动检索，SearXNG移除14个相关入口并启用Bing回退；默认验证返回10条，PubMed/Crossref/模型连接正常。Wayback响应校验、注册策略覆盖及代理探针/空闲关闭分类已部署，最终330项回归通过。当前32个安装模块与工作区一致，挂载relay脚本另外核验哈希；完整恢复/回滚及失败记录见search-stability-20261016.md。此前启动/代理记录中的旧镜像与空结果由本节及最终验收记录更新；未完成的DNS、参考库和M3-A第6项仍需继续。

## 生物医学来源收敛（2026-10-16）

按用户要求，将根Compose中29个内置适配器及Library的Agent/自动搜索开关显式固定，仅PubMed、SearXNG为true；SearXNG配置改为keep_only=[bing]，避免无关来源和此前失败后端参与。此为后续默认配置，取代上文四来源暂停及恢复方式；恢复某来源需修改Compose对应开关，恢复SearXNG后端另改settings.yml。用户动态注册的Collection/Retriever未在本轮逐项禁用；手动显式调用接口仍保留。

修改compose.yaml、.env.example、deployment/searxng/settings.yml；未修改Python核查代码或重建镜像。配置备份位于/data/ningh/nh/ldr-test-5002-backups/biomedical-sources-20261016-155724，含私有配置，不提交。仅重建5002应用容器并重启其SearXNG，保留数据卷；5000/5001未重建或重启，共用仓库配置未来重新加载时可能应用本轮配置。

Compose校验及git diff --check通过。5002实际安装的注册器在全内置来源旧开启快照下，Agent/自动候选均仅pubmed、searxng；SearXNG实际配置仅bing，生物医学查询返回7条且无unresponsive_engines；PubMed查询返回预期PMID33567185。三个容器healthy，登录HTTP200。证据docs/biomedical-sources-20261016.json；本轮为配置与连通性验证，不证明长期稳定性，不改变M3-A第6项未通过状态。未提交、推送或合并。

## 5002应用更新与重启（2026-10-16）

用户要求重启5002查看当前效果，已将私有.env.test-5002的ASTRO_DRA_IMAGE更新为astro-dra:advisory-20261016，并使用同一Compose项目以up --no-build --no-deps重建应用容器。实际镜像sha256:4d848ee3f457f25031847e9cc36adaea327aaaf8645dce08d333d33fdec4c196，与隔离验收版本一致；本轮无需重新构建镜像。只更新应用，SearXNG和relay保持运行，5000/5001未操作。

应用healthy，5002登录HTTP200；安装的publication.py哈希匹配工作区，容器内关闭辅助核查的正文保留烟测通过。原astro-dra-test-5002_ldr_data/ldr_config卷保持一致，账号和历史记录保留。证据advisory-deploy-5002-20261016.json，checks_passed=true。更新前配置与容器记录备份/data/ningh/nh/ldr-test-5002-backups/advisory-deploy-20261016-164349；私有配置不提交。未自动创建新研究任务，旧报告不重写，新研究才体现新流程。未提交/推送/合并。

## 5002引用方括号与顺序修复（2026-10-16）

用户反馈参考文献没有[]且乱序。确认为上轮清理引入的排版回归：新发布器用[N](url)导致Markdown可见标签仅N，同时保留检索原编号，绕过原有首次引用编号整理。该排版功能不属于应删除的核验门槛。

新增research_verify/citation_display.py，独立处理正文首次引用编号、同篇去重、可见[[N]](url)及书目同步重建。schema升为2.1，original_indices记录原编号到展示编号关系，citation_audit_numbering=original使原文核查位置和原编号保持可追溯；不执行额外语义判断或删句。缺失来源编号不分配给其他文献。兼容原始/已链接/双括号/中文数字引用，代码块、参考文献后讨论保留。Quarto支持双括号超链接规范化。有效旧schema 2.0在页面装配和导出时只读整理，原数据库和历史聊天消息不重写。

改动publication.py、claims.py、report_assembly_service.py、quarto_exporter.py及对应测试/验收脚本，更新当前流程说明。258 passed（1.79s），git diff --check通过；Markdown实际HTML输出<a ...>[1]</a>，乱序原索引9/3转1/2且重复引用保持1。新镜像astro-dra:citations-20261016，ID sha256:9c44b43188b328b43bf9d9a19f44e4ae44bdfc2859149417c06aadbbb1621e07。固定合成两篇来源验证普通/详细、真实SQLite/文件/装配、Quarto/LaTeX/ODT/PDF/RIS五种导出，以及旧报告只读转换均通过，证据citation-display-20261016-final.json；此为排版验证，不是生物医学语义验收。

已将5002私有env镜像标签更新并仅重建应用，healthy、登录HTTP200，安装的citation_display/publication/claims哈希匹配工作区，连续编号烟测通过。原ldr_data/ldr_config卷保持，5000/5001及SearXNG/relay未重启。证据citation-display-deploy-20261016.json。代码修改前备份before-citation-format-20261016-172038/code.tar.gz，部署前配置备份citation-deploy-20261016-172946，均位于/data/ningh/nh/ldr-test-5002-backups下，私有配置不提交。Git fetch仍因认证失败，未提交/推送/合并。后续仍为开源引用支撑方法调研和独立真实样本评估，不恢复强制删改规则。


## 5002新增Qwen Flash基础模型（2026-10-16）

用户提供6183端口OpenAI兼容接口，已接入5002作为额外研究模型，原默认openai_endpoint / deepseek-v4-flash保留。复用原生llama.cpp提供方，独立地址http://27.30.76.162:6183/ai/v1，无需密钥；实际模型ID由/models返回，包含Qwen3.8-Flash-Next-GGUF/UD-Q4_K_XL。私有.env.test-5002配置独立LLAMACPP URL并把IP加入NO_PROXY；根Compose与.env.example增加可选地址/密钥映射。

原前端将环境默认模型/提供方禁用，虽然后端支持按任务覆盖，仍无法从页面选择。新增两份固定镜像前端overlay（research.js、settings_sync.js）：允许研究表单按次选提供方/模型，两个自动保存入口均跳过环境锁定默认值；切换提供方清空旧模型及隐藏ID，防止旧ID误投。全局设置的环境锁与出口策略禁用项保留。安装器增加JS overlay类型，继续检查安装目标存在；Python仍做AST检查。页面重新加载恢复默认DeepSeek。普通/详细研究使用所选模型；聊天会话仍沿用原生默认模型逻辑。

5002已部署astro-dra:qwen-flash-20261016，healthy、登录HTTP200，两个实际HTTP静态文件与工作区哈希一致；原数据卷保留，其他现存容器ID/启动时间均未变化。部署前私有配置备份/data/ningh/nh/ldr-test-5002-backups/qwen-flash-20261016-174148，恢复时使用其中原env和Compose配置及原镜像标签。

验证：258 passed；JS语法检查和scripts/check_model_selection.cjs通过，覆盖默认加载、可选模型、原禁用选项保留、切换清空、禁止写回锁定默认值、实际研究提交的提供方/模型ID。scripts/check_qwen_flash.py在部署后的真实容器验证模型发现、原生可用性、get_llm中文回复、流式输出、结构化工具调用和结果回传。证据qwen-flash-smoke-20261016.json与qwen-flash-deploy-5002-20261016.json。未执行完整生物医学研究和质量比较，此烟测不说明Qwen的幻觉率更低。未提交/推送/合并；本轮GitHub认证仍不可用，未能确认远程更新。

使用：浏览器强制刷新5002，在研究高级选项的Model Provider选择llama.cpp，点击刷新模型列表，选择包含Qwen3.8-Flash-Next的模型，再开始研究。后续方向仍为开源引用支撑核验方法调研和真实样本评估，不恢复强制规则删改。
