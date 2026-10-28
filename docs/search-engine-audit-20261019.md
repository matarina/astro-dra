# LDR 搜索引擎实测报告

实测日期：2026-10-19，北京时间约09:25—09:31；报告整理与静态检查随后完成。

结论：5002 当前启用的 PubMed、SearXNG/Bing 均能检索。5000、5001 的默认 SearXNG 当次都返回零条。项目中其他引擎的故障分属代理路径、失效凭据、限流、缺少配置和缺少自建服务，不能统一解释为“搜索引擎不能用”。

机器可读的29引擎状态、全部探测引用与原始证据索引见[汇总JSON](search-audit-summary-20261019.json)。

## 范围与判定方法

- 枚举实际安装注册表中的全部29个内置引擎，检查安装默认配置与容器环境；对具备前置条件的适配器真实发起查询。共73次适配器探测，含失败复核、临时代理对照、直接实例化、内容获取与正常`run()`路径检查。
- 检查5000、5001、5002三个属于本项目的实例；同机其他独立实验项目未纳入。运行镜像、源文件SHA256、启动时间与健康状态见[运行快照](search-audit-runtime-20261019.json)。
- 对SearXNG做23次与文本研究有关的默认/指定后端查询，并记录完整后端配置清单。没有把数百个可选图片、影音、翻译、地图后端当作LDR独立搜索适配器逐个访问。
- 可用指当次真实返回结构化结果；配置存在、HTTP 200、页面健康均不单独构成可用证据。正文提取另行检查，摘要不算论文全文。
- 默认请求2条；部分项目适配器从全局设置重新读取数量，实际返回25条或8条。每次适配器预算65秒，单次requests超时上限18秒，少量并发；没有执行真实模型改写、相关性评分或完整报告生成。
- 审计快照来自**已安装默认值+容器环境变量**，未解密个人账号数据库。因此“缺密钥”指本轮可核实的部署配置中缺少凭据，不排除用户另外在自己的账号里保存过密钥。
- 没有更改服务配置、永久启用来源、替换密钥、重启容器或创建研究任务。9876对照只改变测试子进程环境。报告和JSON不保存API密钥、私有文档或抓到的全文。

## 三个实例的实际情况

| 实例 | 应用代理 | PubMed | 默认SearXNG | 关键区别 |
|---|---|---|---|---|
| 5000 | 2081 | 成功，25条 | HTTP 200，但0条 | 对接宿主8888旧SearXNG；google cse、wikidata、wikipedia超时；多个独立API出现TLS EOF |
| 5001 | 应用未配置代理 | 成功，25条 | HTTP 200，但0条 | 默认google/brave/startpage超时，duckduckgo连接错误；显式指定Bing另测成功10条 |
| 5002 | 9876 | 成功，25条；指定PMID返回1条 | 成功，原始7条，适配器取2条 | SearXNG实际仅安装Bing；未报告失败后端；正常`run()`路径两引擎均成功 |

5002的29个内置引擎环境开关中，仅PubMed与SearXNG允许Agent/自动搜索，其余为false。**其他引擎独立探测成功不代表它们已经参与5002的报告。** Library也显式关闭。5000/5001的环境开关和镜像与5002不同，不能套用同一结论。

证据：[5000首轮](search-audit-5000-20261019.json)、[5001首轮](search-audit-5001-20261019.json)、[5002首轮](search-audit-5002-20261019.json)、[5002正常调用路径](search-audit-5002-pipeline-20261019.json)。

## 全部29个内置引擎及工作分工

下表“5002成功”包含手动显式探测；除PubMed/SearXNG外，自动来源开关保持关闭。“需配置”表示未具备真实认证搜索条件，不能据此断言供应商服务故障。

| 引擎 | 对应工作 | 当次判定 | 具体证据、失败原因或使用限制 |
|---|---|---|---|
| PubMed | 生物医学论文发现、PMID/DOI等元数据、摘要，按配置尝试PMC全文 | 可用 | 三实例均成功；5002指定PMID33567185准确返回目标论文，摘要2786字符，`content_type=abstract` |
| SearXNG | 聚合网页/文献发现，依赖所选后端 | 5002可用，其他实例默认失败 | 5002 Bing原始7条；5000/5001默认0条并报告上游错误；5001显式Bing10条 |
| arXiv | 计算机、物理、数学等预印本文献 | 可检索 | 5000、5002各25条；本轮未下载PDF，过去的限流记录不能替代本次结果 |
| OpenAlex | 跨学科论文、作者、期刊、引用与开放获取信息 | 可检索 | 两实例各2条；当次未提供OpenAlex key仍返回200；内容样本791字符，不视为论文全文 |
| Semantic Scholar | 学术论文、摘要、引用网络、TLDR | 当前失败 | 两实例均0条；HTTP客户端重试最终抛RetryError，原因链明确为`too many 429 error responses`，即限流 |
| NASA ADS | 天文、天体物理文献 | 需配置 | 部署没有NASA ADS API token，工厂返回None，未做认证搜索 |
| Exa | 语义网页发现、抽取网页文本，适合概念相关检索 | 可检索 | 5000返回2条；文本样本523字符；不能据此保证任意论文全文可得 |
| Tavily | 面向研究代理的网页检索与内容提取 | 可用但旧路径不稳定 | 首轮2081成功，内容复核时TLS EOF；临时9876复测成功2条，样本`content`164624字符 |
| Serper | Google结果API，用于通用网页发现 | 可用但旧路径不稳定 | 首轮成功2条，2081复核TLS EOF；临时9876成功2条。样本为搜索片段，正文需独立抓取 |
| SerpAPI | Google等搜索结果的结构化API | 可检索 | 5000两次均成功，8条；本轮内容样本仍为片段 |
| Brave | 通用网页发现、时效信息 | 需调整代理路径 | 2081下TLS握手EOF、0条；同一凭据仅在测试进程改走9876后HTTP 200、2条 |
| Google PSE | 按指定站点/范围检索Google自定义搜索索引 | 需配置 | 缺API key，工厂返回None；接入还需核对自定义搜索引擎ID（cx） |
| Mojeek | 独立网页索引检索 | 需配置 | 缺API key，工厂返回None，未做认证搜索 |
| ScaleSERP | 结构化Google搜索结果 | 需配置 | 缺API key，工厂返回None，未做认证搜索 |
| Sofya | 网页检索及抽取内容，供AI代理取证 | 需配置 | 缺API key，工厂返回None，未做认证搜索 |
| TinyFish | 网页检索与网页内容获取 | 需配置 | 缺API key，工厂返回None，未做认证搜索 |
| DuckDuckGo（ddg） | 无独立付费key的通用网页发现；Wayback可用其发现URL | 底层可用，默认注册配置缺失 | 有模块和硬编码注册项，但安装默认设置中无`search.engine.web.ddg.*`，工厂拒绝Unknown engine；5002直接实例化适配器成功1条。不能把这次底层成功等同于现有工厂路径可用 |
| GitHub | 开源项目、代码、README与Issue检索 | 当前凭据失败，可修复 | 现有token在2081/9876均401 `Bad credentials`；直接实例化不传token并走9876，匿名仓库检索成功2条。工厂目前要求key，不会自动采用此匿名路径 |
| Wikipedia | 百科背景、术语解释 | API适配器当前失败 | 5000 API502；5002搜索部分步骤200，摘要请求继而429，最终0条。普通文章HTML抓取另测成功，不能说整个Wikipedia站点不可访问 |
| Wikinews | 新闻事件发现、时间线资料 | 5002可检索 | 5000连续读超时；5002返回2条 |
| Guardian | Guardian新闻报道检索及正文 | 需补默认配置与key | 同ddg，模块/注册项存在但安装默认设置中缺引擎配置；工厂Unknown engine；直接构造读取缺失key设置时失败，未发认证搜索 |
| Wayback | 指定URL的历史快照、失效页面追溯 | 5002可检索 | 5000访问CDX接口TLS EOF；5002相同URL返回3个快照。测的是已知URL快照发现，未验收关键词经DDG发现URL或快照正文 |
| PubChem | 化合物名称、CID、结构性质与说明 | 可检索 | 两实例各2条，测试词aspirin；适合化合物事实，不能代替临床论文 |
| Zenodo | 数据集、软件、预印本及其他科研产物 | 可检索 | 两实例各2条；未下载数据文件 |
| StackExchange | 技术问答、实现方案与常见错误 | 可检索并获取正文 | 两实例各2条；5002问题/回答内容样本5996字符 |
| Gutenberg | 公版书籍、历史著作及正文 | 可检索并获取正文 | 两实例各2条；Pride and Prejudice文本样本50146字符，为配置截断后的正文 |
| OpenLibrary | 图书书目、作者、版本、ISBN与借阅/阅读线索 | 5002可检索 | 5000 TLS EOF；5002返回2条。书目可得不代表整本书开放下载 |
| Elasticsearch | 用户自建索引的私有文档检索 | 当前缺后端 | 默认`localhost:9200`连接拒绝，工厂创建失败；依赖包存在，原因是配置地址没有运行中的可达ES服务 |
| Paperless | 自建Paperless-ngx档案与OCR文档检索 | 需配置 | 配置enabled=false、缺API token，默认服务地址localhost:8000；认证前置条件不成立，未据此宣称真实Paperless服务宕机 |

复核证据：[5002扩展探测](search-audit-5002-expanded-20261019.json)、[缺配置复核](search-audit-5000-recheck-20261019.json)、[Brave/GitHub代理对照](search-audit-5000-proxy9876-20261019.json)、[DDG/Guardian直接构造](search-audit-5002-direct-20261019.json)、[GitHub匿名9876对照](search-audit-github-anonymous9876-20261019.json)。失败的匿名2081测试另保存在[原失败记录](search-audit-github-anonymous-20261019.json)。

## SearXNG后端与独立API为什么结论不同

5000的SearXNG `/config`列出261个后端、79个默认启用；5001为247/85；5002实际只有Bing一个。数字是可枚举配置数量，不能当作可用引擎数量。

对5000旧SearXNG的15个相关后端逐个查询：

| 后端 | 结果 | 暴露出的原因 |
|---|---|---|
| Europe PMC | 成功20条 | 可作为生物医学候选发现来源，但当前5002未启用 |
| Bing | 0条 | 没有返回unresponsive错误，原因未被此接口明确暴露，不能猜成密钥或单纯超时 |
| Wikipedia | 0条 | 已因超时被临时挂起`Suspended: timeout` |
| Google CSE | 0条 | `server API error` |
| Semantic Scholar | 0条 | `access denied` |
| Google、Google Scholar、arXiv、PubMed、OpenAIRE Publications、GitHub、StackOverflow、Wikinews、DuckDuckGo、Brave | 均0条 | 各自后端报告timeout |

5001额外显式测试Bing/Google/Brave/DDG/Startpage：仅Bing成功10条；其余timeout或HTTP connection error。独立PubMed/arXiv/StackExchange适配器成功而SearXNG对应后端超时，说明**接入路径、适配实现、网络和上游预算**影响结果，不能据此判断这些内容源整体不可用。

原始证据：[三实例配置与相关后端](search-audit-searxng-backends-20261019.json)、[5001指定后端](search-audit-5001-backends-20261019.json)。

## 摘要、全文和辅助服务

| 能力 | 实测 | 正确解读 |
|---|---|---|
| PubMed指定PMID | 目标论文、2786字符abstract；enriched `full_content`26649字符 | 字段名和长度不代表全文；明确`content_type=abstract`，其中还包含扩展元信息 |
| Europe PMC检索 | HTTP 200，1条样本、hitCount 258722 | 补充的生物医学发现服务；不是新增LDR内置适配器 |
| Europe PMC开放全文XML | PMC13647138，200，316875字节，存在`<body>` | 已证明该开放论文的正文XML可获得，不代表所有论文全文可得，也未把此接口接入主流程 |
| Crossref DOI接口 | DOI10.1038/nature14539，200，返回Deep learning | 适合身份/出版元数据核对；不是全文数据库，也不是新增自动检索引擎 |
| 通用网页提取 | LDR实际`batch_fetch_and_extract`，NCI页面14499字符、Wikipedia文章141752字符 | 网页抓取与搜索API是两步，API429不等于普通HTML无法获取；JS渲染关闭 |
| Tavily | 9876路径内容样本164624字符 | 成功取回内容；未独立逐段核对全文完整性 |
| Exa | 返回text523字符 | 能取文本，样本较短；不夸大为全文 |
| Serper、SerpAPI、SearXNG | 本轮直接内容检查仅留下片段 | 无LLM上下文时，基类仅在`include_full_content and llm`成立时初始化通用full_search辅助器；本轮未提供LLM，因此此处不构成生产全文抓取故障，通用抓取函数已另测成功 |
| Gutenberg / StackExchange | 50146 / 5996字符正文 | 公版图书与问答正文获取成功 |

证据：[指定PubMed论文](search-audit-pubmed-knownpaper-20261019.json)、[5002内容检查](search-audit-5002-content-20261019.json)、[5000内容首轮](search-audit-5000-content-20261019.json)、[内容9876复核](search-audit-5000-content-proxy9876-20261019.json)、[生物医学辅助服务与网页提取](search-audit-biomedical-services-20261019.json)。JSON中`search_and_content_checked`表示调用过内容步骤，是否拿到内容必须结合content字段长度和content_type判断。

## Library、Collection和自定义Retriever

三者是本地/用户注册的检索能力，不是额外的公共搜索网站：Library搜索全部资料库，Collection搜索单个集合，Retriever封装用户提供的LangChain检索器。

三实例均能发现sentence_transformers、FAISS等依赖；在本轮可检查的数据路径内未找到`.faiss`索引，5002的Library Agent/auto开关关闭。新审计进程的共享Retriever列表为空，但注册表是进程内状态，**这不能证明Web工作进程没有注册Retriever**。

由于未读取个人数据库、未取得账号会话，也未构造带私有文档的测试集合，本轮将其标为“未完成账号级检索验收”，不冒充“已通过”或“服务坏了”。证据：[本地检索依赖与索引检查](search-audit-local-rag-20261019.json)。

## 修复优先级与限制

1. 若继续使用5000/5001，先处理默认SearXNG零结果和旧代理路径。Brave的2081/9876对照、Tavily/Serper的重试差异说明需要统一并验证出口；本轮只诊断，未替换这些实例的配置。5001显式Bing成功提供了可复核的修复候选。
2. GitHub更换有效token；若采用匿名检索，需同时处理工厂requires_api_key约束和更低的匿名限额。不能仅删token就宣称当前工厂路径修好。
3. Semantic Scholar、Wikipedia按429做有限退避/冷却；补合规客户端标识或合适认证，避免反复即时重试。Wikipedia返回体明确指向[Wikimedia限流文档](https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits)，官方说明了User-Agent、并发与Retry-After要求。页面HTML和API采用不同路径，结果可不同。
4. DDG补齐默认引擎设置后再测完整工厂/Agent路径；Guardian还需key。其余付费/需认证引擎分别补自己的凭据，不能混用其他供应商key。
5. ES、Paperless、Library按实际使用需求配置服务、资料与索引，然后用账号级查询验收。对于生物医学工作，已测通的PubMed、OpenAlex、Europe PMC有明确用途，但恢复自动来源需要单独配置变更；本轮未自动扩大来源池。

这是小样本可用性和故障定位，不是长期可用率、中文召回率、领域相关性、完整论文全文覆盖率或报告事实准确率验收。Bing样本前列包含宽泛Cancer介绍页，不能从“7条”推断专业问题的召回充分。缺少凭据的远端服务没有完成真实认证查询。

## 复跑

[审计脚本](../scripts/audit_search_engines.py)使用容器内现有依赖与凭据；不会把凭据拷到宿主报告。输出文件已存在时拒绝覆盖，保留失败记录。

```bash
python3 scripts/audit_search_engines.py \
  --container astro-dra-test-5002-local-deep-research-1 \
  --engines pubmed searxng --mode pipeline \
  --output docs/search-audit-next-run.json
```

可用`--mode full`检查一个结果的内容字段；`--mode direct`仅用于区分底层适配器和工厂接线；`--proxy http://host.docker.internal:9876`仅影响测试子进程。正常适配器探测的默认快照没有个人设置，复跑比较时应固定镜像与环境，并明确这一边界。
