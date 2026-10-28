# 检索阶段恢复与改进（2026-10-20）

本轮按用户要求先比较原始 LDR、5000 和 5002，恢复可复现的检索参数基线，再只修改检索模块。自动/Agent 文献发现来源明确为 **PubMed、SearXNG、Europe PMC**；默认主引擎保留 SearXNG，策略仍为 langgraph-agent，实测模型仍为 deepseek-v4-flash。

代码已在工作区完成，并安装到与当前5002镜像/网络相同的一次性容器中验证。**没有部署到运行中的5000或5002**，没有重启服务、修改代理或SearXNG后端配置。两服务镜像、启动时间保持不变，均healthy。机器检查见[search-recovery-20261020.json](search-recovery-20261020.json)。

## 原始版本与两实例的差异

5000并非完全未改动的上游版本。本次另外从其固定上游基础镜像提取了原始模块，避免把5000早先的定制当作LDR原生行为。三者均为LDR 1.10.7。

| 项目 | 原始基础镜像/5000 | 5002安装版本 | 本轮处理 |
|---|---|---|---|
| SearXNG适配器、BaseSearchEngine、工厂、相关性过滤器 | 三份代码SHA相同 | 同左 | 不回滚到另一个相同的适配器；定位实际启用和提示问题 |
| 单次候选上限/筛后上限 | 5000环境明确12/6 | 环境缺少这两项，回到50/20默认值 | 恢复12/6；PubMed不再把小于25的请求强行提高到25 |
| 全局skip_relevance_filter | 5000为false | 未设置，默认true | 恢复false，但这不足以实际开启SearXNG过滤 |
| SearXNG过滤实际启用 | 工厂只有检测到引擎属性或显式单引擎开关才启用；全局false分支未设true | 同一逻辑 | 明确给三个引擎设置enable_llm_relevance_filter=true |
| SearXNG后端 | 5000连接旧8888服务，后端较多 | 当前独立SearXNG仅启用Bing | 本轮不盲目恢复全部后端；Bing原始偏题仍是未修复的上游问题 |
| PubMed查询处理 | 原版已有“优化时不要日期”、按命中量改最近1/3/5年和零结果简化机制 | 基本沿用 | 禁止第二次擅自放宽平台/日期；默认关闭适配器二次查询优化 |
| 摘要和元数据XML | 原版两个函数分别EFetch；摘要解析使用.text | 同类问题 | 一份EFetch缓存复用；itertext保留内嵌标签前后文字 |
| Agent常规来源80上限 | 原始上游与5000不同；5000已定制加入此上限 | 沿用 | 本轮保留；不能把该问题归因于5002之后的新补丁 |
| Europe PMC独立适配器 | 没有；旧SearXNG有同名后端不等于LDR独立工具 | 没有 | 新增独立适配器、注册项、受信模块及设置 |

结论：确有后续配置变化扩大了每次进入流程的候选量，也收窄了SearXNG后端；同时，过滤启用逻辑、PubMed查询改写、重复请求和摘要解析问题原版就存在。此前“5000配置了过滤，所以过滤一定正常”的推断不成立。

## 先恢复，再修改的验证过程

`deployment/search-restoration-profile.json`记录5000的四项参数：主引擎searxng、skip=false、候选12、筛后6。先在5002原镜像的一次性容器中只覆盖这四项，不安装代码补丁。

冻结第一轮研究留下的10条篮球网页，保持内容与查询不变：

| 隔离方案 | 实际开启SearXNG过滤 | 保留的偏题网页 |
|---|---:|---:|
| 当前5002安装版 | 否 | 10/10 |
| 只恢复5000四项参数 | 否 | 10/10 |
| 明确开启单引擎过滤，但沿用原提示 | 是 | 中间实测仍被全选，按上限返回6条 |
| 本轮最终检索补丁 | 是 | 0/10 |

中间结果说明不能仅凭开关判断质量。原提示没有明确零相关时应返回什么，实测模型对两批篮球材料直接返回`0, 1, 2, 3, 4`。现在明确允许`[]`、要求主题匹配、禁止为了非空而选择结果。索引解析只接收明确数组或兼容的纯逗号数字列表，不再从解释性文本任意抽取数字。

改提示过程中也出现过PubMed一批候选全部被拒绝的中间结果。因此同时修复材料不足：原版PubMed预览只取摘要前500字符，过滤器又限制片段800字符。现在预览记录保留完整摘要，筛选优先读摘要（单篇最多8000字符），不会只看标题和摘要开头。最终再用“8条篮球网页+1篇真实相关论文”的混合材料验证，保留相关论文、剔除8条网页。中间失败结果保留，未只保留成功记录。

## 当前检索路径

1. Agent按原策略选择`web_search`（默认SearXNG）、`search_pubmed`或`search_europepmc`。其余原生引擎不进入自动/Agent来源池；fetch和子研究工具继续保留。
2. 每次搜索候选默认12条，相关性筛选后最多6条。PubMed专用工具说明补充其字段/布尔语法，Europe PMC说明使用FIRST_PDATE语法，避免两者查询语法混用。
3. PubMed按收到的结构化查询搜索；不再按命中量自动限近一年/三年，也不在零结果时删平台或日期。关闭的是适配器二次改写，Agent仍负责构造查询。显式days_limit仍尊重用户设置；可选自然语言优化保留，但丢年份/引号实体时退回原查询。
4. PubMed先ESearch、再ESummary、再EFetch。摘要和详细元数据复用同一批XML，并缓存到该引擎实例，避免成功元数据XML含摘要却未利用。XML每段只读一次，保留内嵌基因/上标/强调文字及尾部文本。
5. NCBI请求通过共享文件锁节流，同一数据目录下的引擎实例和工作进程共用请求间隔；临时网络错误及429/部分5xx最多尝试3次，尊重有界Retry-After。Europe PMC也使用LDR受保护HTTP客户端和独立节流。
6. Europe PMC使用`resultType=core`，一份响应取得标题、作者、期刊、日期、DOI、PMID/PMCID、出版类型和摘要。链接指向具体论文记录，保留MED/PMC/PPR等记录来源，不把预印本或缺摘要的记录宣称为合格期刊论文。
7. 学术材料进入相关性筛选后，交给现有收集器去重和编号。学术工具片段统一带身份、出版类型及证据层级，摘要最多展示8000字符，超过时明确标注截断；来源记录保留完整摘要。缺摘要明确显示metadata only。

工具可见材料示意：

```text
[N] 论文标题 (具体论文URL)
Title: ...
Journal: ...
Date: ...
DOI: ...
PMID: ...
Publication types: Journal Article
Evidence level: abstract
Abstract: 原始摘要文本……
```

没有改最终写作、引用重排或报告发布流程。原生科学引擎的DOI→OpenAlex元数据补充仍存在；它不作为第四个文献搜索工具。期刊声誉评分也不等于JIF。

## 最终验证与文件

最终实测使用实际工厂和`engine.run()`，不只调用自制HTTP脚本：

- SearXNG当次仍返回10条偏题网页，最终均被相关性筛选剔除；上游没有因此恢复正常。
- PubMed：已知PMID41107232返回1篇、完整1200字符摘要；限定日期Visium HD查询12条候选→6条，均保留摘要。
- Europe PMC：同PMID查询返回1篇，DOI和完整摘要与PubMed一致；限定日期查询12条→6条，均保留摘要。
- 两个学术引擎返回的同论文经实际安装版SearchResultsCollector合并为一个来源。现有重复来源返回空批次的行为仍保留，未将它当成本次修复。
- 每项PubMed查询只发生一次EFetch，最终探针NCBI请求未出现429；这不是长期不再限流的保证。
- 实际Agent工具表为web_search、search_pubmed、search_europepmc、fetch_content、research_subtopic。Agent、research_service和report_generator安装文件的SHA保持原镜像不变。
- 16项隔离检查通过；最终完整回归**280 passed（2.82s）**，Compose解析及diff空白检查通过。

主要文件：

- `local_deep_research/search_engine_pubmed.py`：查询范围、XML复用、摘要和工具片段。
- `local_deep_research/overlay/relevance_filter.py`：基于原始同版本过滤器的提示及索引解析改动。
- `local_deep_research/overlay/search_engine_europepmc.py`：新增独立引擎。
- `local_deep_research/research_verify/retrieval.py`：共享请求节流、重试、学术片段格式。
- `local_deep_research/search_defaults.json`、`compose.yaml`、`.env.example`：恢复参数和三源开关。
- `deployment/search-overlay-manifest.json`：只含6个检索安装目标；`install_overlays.py --search-only`仅额外安装retrieval.py，拒绝混入报告/Agent目标，不复制此前其他research_verify改动。
- `scripts/check_search_recovery.py`：installed/restored/patched三个隔离方案。
- `local_deep_research/tests/test_search_recovery.py`：XML/约束、跨进程节流、重试、摘要可见性、索引解析、零结果与安装隔离回归。

复验命令（在一次性容器内安装，输出必须使用不存在的新路径）：

```bash
PYTHONDONTWRITEBYTECODE=1 /data/ningh/nh/verify-venv/bin/python -u scripts/check_search_recovery.py \
  --variant patched --output /data/ningh/nh/ldr-experiments/search-recovery-20261020/new-probe.json
```

原始/5000/5002安装文件快照、工作区改动前备份、全部中间与最终探针在仓库外`/data/ningh/nh/ldr-experiments/search-recovery-20261020/`。脚本使用当前5002的模型环境并仅在内存转交凭据；原始响应和材料未放入Git。当前脚本的冻结材料路径依赖本机首轮诊断产物。

## 限制与下一步

本轮验证检索链，**没有重新完整生成空间转录组报告**，没有证明论文全集覆盖或JIF>10筛选已经实现。提示改进及小样本正反例不能替代独立召回/准确率评估。不同时间SearXNG可能返回偏题或零条，仍需修复其上游；没有将过滤后零条伪装成搜索服务正常。

共享节流只覆盖使用同一数据目录的实例/进程，其他部署共用出口IP仍可能触发NCBI限流。沿用原过滤器的异常降级机制：个别判断失败跳过，全部批次失败时返回有上限的未筛候选，不能宣称错误材料永远不会进入来源池。

下一阶段仍需处理来源池80名额及重复来源反馈、网络故障与真实零命中的区分、JIF与论文类型核实、全文获取、最终写作材料保全、范围引用重排。最终报告的引文支撑一致性尚未整体解决。本轮没有提交、推送或合并；git fetch仍因既有GitHub HTTPS认证不可用失败。
