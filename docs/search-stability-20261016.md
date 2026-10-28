# 检索稳定性修复与临时来源暂停

日期：2026-10-16；分支work/ldr-20261012。
状态：本轮暂停策略、适配器响应校验、代理日志分类及通用搜索回退已在5002测试实例验证生效。
本轮未合并main、推送或重建5000/5001服务；工作区仍有此前M3-A第6项未提交改动，本次也尚未提交。

## 实际调整

1. 根Compose暂停arXiv、Semantic Scholar、Brave的Agent及自动检索。DDG开关同时约束Wayback的间接DuckDuckGo URL发现；当前基座没有独立ddg注册条目，不能只靠未知设置键判断暂停成功。
2. SearXNG通过use_default_settings.engines.remove实际移除上述来源以及DuckDuckGo、Startpage，共14个入口（含图片/新闻等变体）。保留PubMed、OpenAlex、SearXNG；显式启用已实际返回结果的Bing作通用搜索入口。
3. 新增search_policy.py及search_engines_config覆盖补丁：在注册阶段重新应用环境开关，覆盖旧/部分任务快照中的过期值，不污染原快照；开关可恢复，非法布尔值按停用处理且不打印原值。仅关闭自动/Agent资格，不把手动显式调用接口改成新的全局禁止API。
4. Wayback覆盖补丁来自实际固定镜像模块（原始SHA256 80950329f756e5b89777028df63f10cd1dee634e11af2d6d8d3ac39c73f5c119）。四个快照入口检查HTTP状态、明确HTML类型、JSON解析及结构；兼容有效text/plain/无类型JSON。合法空结果保持为空；上游失败抛出WaybackResponseError（reason_code/status/content_type），429仍交给既有RateLimitError路径。错误消息不含响应正文或请求查询。
5. Wayback自然语言URL发现遵守DDG暂停策略；显式URL查询仍可用。SSRF和DNS绑定防护保持启用。
6. relay先读取客户端首字节再连上游，空TCP探针不再创建上游连接。真实错误记录方向、阶段及已转发字节数；正常空闲关闭记录proxy_relay_idle_close/info，实际连接/读写失败保留proxy_relay_transport_error，二者不再都显示成无原因TimeoutError。

注册器原始SHA256：14bd78f72e955b8bbb2625be70235eff9eb56fd69edf58a69f17b667b15118b6。
两个上游模块均列入deployment/overlay-manifest.json，本轮清单共13项；不能仅改旁置local-deep-research源码。

## 验证与失败记录

- 最终全量330 passed（1.69s）；本轮新增65项。覆盖旧快照、恢复开关、未知间接DDG、错误HTTP/HTML/JSON/结构、合法空响应、所有快照入口、实际TCP双向大数据/半关闭、真实RST/连接拒绝和正常空闲关闭。
- 镜像astro-dra:search-stability-20261016-v2，manifest/image ID sha256:fc50ef18b85cc5943cf5965be121dd36d1fe01e3fb14403a73a0a29731220bad；config sha256:9c907e06ef64b20ef249fea9e61f14ec4a2934839222283ff3362e35dc47a975。relay脚本通过只读挂载，最终脚本SHA见补充记录；只改挂载脚本需要重启relay，无需重建应用镜像。
- 一次性无网络容器验证实际注册器：暂停来源在Agent/自动候选池均为空，未触发其可用性探测；PubMed/OpenAlex/SearXNG配置保留。13个覆盖模块+19个research_verify模块共32个文件与工作区SHA256一致。
- 第一轮真实运行记录search-stability-runtime-20261016.json保留checks_passed=false：暂停和代码检查已通过，但SearXNG默认查询0条。该文件部分验证模块哈希键多了一层路径前缀，后续汇总只规范化键名，不改变哈希值。
- 单独核验Bing返回10条；Google0条，Mojeek/Qwant access denied，Yahoo HTTP protocol error。没有开启这些未通过的备用来源。
- 启用Bing后的search-stability-final-20261016.json为true：默认查询10条，结果来源bing，14个暂停入口均不在配置中，网页200。应用进程未变，因此PubMed200/1条ID、Crossref200、模型200直连、32文件及策略检查沿用同一应用容器的前轮记录，文档中明确继承来源。
- 此时日志还存在7条不能区分空闲/读写超时的历史TimeoutError；未把它们强行认定为正常关闭。后续补上reason分类及真实空闲测试，仅重启relay。
- 最终search-stability-relay-final-20261016.json为true：挂载脚本哈希一致，连续5次健康检查成功，旧探针重置日志0条，本轮新传输错误事件0条；经新relay访问Crossref200，网页200。监测窗口有限，不证明长期无网络故障。

## 恢复与回滚

暂停配置是可恢复的。配额/网络确认恢复后，在私有.env.test-5002中按需设置对应的两个变量为true：

    LDR_SEARCH_ENGINE_WEB_ARXIV_AGENT_ENABLED=true
    LDR_SEARCH_ENGINE_WEB_ARXIV_USE_IN_AUTO_SEARCH=true

Semantic Scholar使用SEMANTIC_SCHOLAR，Brave使用BRAVE，DuckDuckGo使用DDG；不要用DUCKDUCKGO作为LDR内部键名。
SearXNG需要另从settings.yml的remove列表中恢复对应名字。两层设置分别管理，且API凭据/配额仍需可用。

应用配置更新：

    docker compose -p astro-dra-test-5002 --env-file .env.test-5002 -f compose.yaml up -d --no-build

挂载的SearXNG文件更新后需显式加载；up不会仅因挂载文件内容变化而重建：

    docker compose -p astro-dra-test-5002 --env-file .env.test-5002 -f compose.yaml restart searxng

旧镜像保留为astro-dra:dev-5002-before-search-stability-20261016。
部署前配置及relay脚本备份位于/data/ningh/nh/ldr-test-5002-backups/search-stability-20261016-133032，目录0700、备份文件0600（含私有env，禁止提交）。
完整回滚应先核对并恢复备份的Compose、SearXNG、relay脚本和私有env，再按同一项目名启动；恢复公共配置/脚本时使用原0644权限，私有env保持0600。不要只换应用镜像却遗留不匹配的挂载脚本；不删除数据卷。

## 剩余问题

- DNS异常和期刊参考库下载/构建未就绪仍需独立排查，本轮没有关闭安全校验或清理下载锁。
- Wikipedia解析健壮性和SearXNG上游超时收尾竞态未在本轮修复。
- 适配器现在抛出明确失败；全链路如何展示来源不可用和统一预算/冷却仍要继续完善。手动暂停不是已实现自动熔断。
- 本轮没有重跑完整生成报告/独立领域审核，M3-A第6项仍待验收；不代表四项文献严格条件已完成。
