# 5002网页任务实时日志检查（2026-10-21）

> 文档定位：当时缺陷；后续runtime/abstract修复部分问题。本页记录当时过程；当前状态见[状态总览](current-status.md)，有效后续见[待办](roadmap.md)。

用户正在网页运行空间转录组问题，要求实时监控日志。本次只读监控及小型离线格式检查，没有修改应用、启停容器、重跑研究或发起额外模型调用。

## 任务和完成情况

- 研究ID：`06641267-b2b2-415a-9759-b506eabde61a`。
- 北京时间13:10:38启动；13:16:28开始综合82条来源；13:17:13生成9120字符正文；13:20:24报告和67条引用来源保存成功，随后出现`Research completed successfully`。
- 总耗时约9分47秒。正文生成后到保存成功约3分11秒，其间DEBUG日志记录130次模型调用开始，符合当前同步辅助引用检查路径；不能将“正在保存”理解成数据库连续写入3分钟。
- 当前镜像为`astro-dra:full-20261020`，ID `sha256:4c860f0abb4a81188ea139337e97cb82ee6b12024f760b5d1b267e8b31f567f5`，于2026-10-20 15:32:44启动。应用healthy、RestartCount=0、OOMKilled=false。
- 模型deepseek-v4-flash、langgraph-agent、主搜索SearXNG。用户这次使用原始中文问题；与前四轮澄清后问句及隔离安装范围不同，不作严格A/B对比。

**运行状态更新**：5002已经更新，不能继续引用旧开发记录的“尚未部署”作为当前事实。只读核实收集器Mixin实际加载，相关检索helper与工作区哈希相同。当前镜像还加载较早的generation与fetch文本保全补丁；与第四轮collection-only隔离测试不完全相同。此次监控没有执行该部署。

## 1. 已确认的错误PMC身份映射，需要优先处理

运行日志13:14:02报告：`Found PMC ID: PMC13678460 for PMID: 35512705`。检查实际安装的`research_library/downloaders/pubmed.py:411`，发现`_get_pmc_id_from_pmid`请求ELink时只指定`dbfrom=pubmed, db=pmc`，随后对任意`dbto=pmc`关联取第一条，没有限定`linkname=pubmed_pmc`。

运行结束后通过同一容器进行两次公开NCBI API只读核查，均HTTP200：

- ELink对PMID35512705只返回`linkname=pubmed_pmc_refs`，共有1042个关联，第一条正是13678460。它是引用关系，不是该论文自身的PMC全文映射。[原始ELink接口](https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?dbfrom=pubmed&db=pmc&id=35512705&retmode=json)
- ESummary确认PMC13678460对应PMID42898662、DOI `10.3389/fimmu.2026.1865949`，标题为“From density to spatial function: spatial multi-omics, composite biomarker design, and therapeutic engineering of tertiary lymphoid structures in solid tumors.”，年份2026。它不是被请求的PMID35512705。[原始ESummary接口](https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pmc&id=13678460&retmode=json)

因此，已经证实当前任务实际发生了错误身份映射，不能当成一般的网络失败。若后续PDF下载成功，存在把另一篇正文挂到原PubMed URL下的风险。但**这次对应下载最终403/非PDF/HTML203后失败，没有日志证据证明另一篇正文实际进入报告**。本次不能据此断言最终报告已经串文，也不能把此前所有引用偏差都归因于该缺陷。

网页抓取兜底还有`re.search(r"PMC\d+", response.text)`取首个匹配的路径；本次未证实走到了该分支，也未验证其具体错例，不能与已确认ELink问题混写。

最小通用修正方向是区分文献自身的全文映射与引用关系，并在拿到正文后核对标识；这属于身份处理，不是该题相关性规则。本轮只记录，不在用户运行中替换下载器。

## 2. 相关性筛选格式解析失败频繁

任务窗口内184条筛选模型返回日志，50个批次报`ValueError: Invalid relevance index selection`：Europe PMC31批、PubMed19批。失败来自`_parse_indices`，不是模型正常判为不相关，也没有证据说明是编号越界；该报错可由JSON格式或类型不符合预期引起。

部分失败批次直接跳过，导致候选损失；4次所有批次失败，回退为未经筛选的前6条候选（PubMed3次、EPMC1次）。这同时影响召回和入池质量。

失败前仅记录模型返回字符数，未在异常路径保留返回文本，现有日志不足以确认究竟是代码围栏、解释文字、对象结构还是其他格式。不能凭猜测放宽解析器或把解释中的数字当引用索引。

另有50条`Parser found no integers`警告；DEBUG样本明确为合法的`[]`。其中“所有完成批次返回空列表”的ERROR文案会误导排障，不能把它们全部算作模型异常。本报告的50个失败批次只统计真正的`Invalid relevance index selection`，没有混入合法空选择。

## 3. 获取全文后仍被前1万字符截断

实际fetch工具`CONTENT_MAX_LENGTH=10_000`，传给ContentFetcher后仅保留开头，追加截断标记。4个可完整解析的FETCH诊断条目均记录10029字符，并带截断标记；不能把这些片段称为全文。

以PMID42056516为例，日志中的抓取片段在字符6825才出现Abstract、8411才出现Main，没有Methods标题；前段大量为作者、机构与版权。工具再按问题提取摘要，不能从未获取到的方法段提取工具和参数。这是前段截断及XML正文提取问题，不只是假设“模型扩写摘要”。另一条40082609片段出现Methods词项，不能据此断言本轮所有页面都没有方法内容。

两次工具最终失败分别是PMID35512705、40882628，前面经历Europe PMC PDF403、非PDF HTML和PubMed HTML203。HTTP403日志8条并不等于8篇论文失败，多层重试会重复记录。

现有保全补丁能保留已经取得的文本，但不能恢复ContentFetcher前端已经截掉的后文。小幅改进应优先保留文章正文结构、按章节定位相关段落，而不是只增加摘要扩写限制。

## 4. 来源预算反馈已生效，选材容量仍受限制

至少到13:13:15日志显示第一步结束已收集81条，常规80来源预算已满（另有fetch单独登记）。之后出现明确的未登记候选反馈及已有编号复用，最后以82条来源综合。

本次可见的19条主进度反馈包含24次复用和37次未登记；这不是整个任务collector的完整统计，子研究的每批结果没有全部出现在主进度中，不能将可见新增14次当作全局只登记14篇。

修正后的反馈能够区分“真零结果”和“池满未登记”，但没有改变先到先得及后续候选难以进入最终来源池的问题。初次达到80条的精确时刻无法仅靠现有主进度日志确定，不能把最早出现的“0 not registered because the source budget is full”字面文案当作满池证据。

## 5. 网页召回弱，JIF取证过程未见明确记录

可见PubMed预览调用50次、SearXNG预览调用22次；Europe PMC适配器未逐次输出同等搜索日志，不能据此宣称总计只搜索72次。

22次SearXNG查询中20次在原始解析阶段返回无有效结果，并非都被LLM筛掉。SearXNG服务访问成功、容器healthy不能等于网页搜索召回正常；后端没有可用异常日志，尚不能判定是Bing限制、查询匹配还是解析问题。

可见的PubMed/SearXNG搜索词中没有专门查询年度JIF/JCR/官方期刊指标，12个fetch地址也均为论文页。日志中的journal reputation threshold=2是声誉等级过滤，不是JIF>10。这些只能说明本轮没有观察到明确的指标核实过程，不能仅凭日志给所有论文判定JIF，也未读取最终正文来核对模型实际说法。

## 6. 当前最终材料格式仍漏显式书目字段

当前5002已经使用`source_material`和`format_source_documents`，会带标题、URL、证据范围，不能再沿用第四轮“旧formatter直接裸full_content”的描述。

但它们没有把来源对象的日期、期刊、DOI显式写入metadata或输出模板。使用实际安装StandardCitationHandler、通用示例记录、无网络/无模型调用验证：标题、URL、摘要进入格式化文本，而日期、期刊、DOI均未进入。原始正文自身含有这些字段时可能仍可见；该检查不证明这次82条来源的字段全都消失。

因此仍存在“数据库对象有字段、模型材料未明确包含”的通用漏点；要核定这次具体年份、期刊错误，需要实际报告及对应材料，不能从日志直接推出。

## 7. 保存进度与同步辅助检查不一致

13:17:13先显示“Saving research report to database”，程序实际先执行`publish_report`及同步辅助引用检查，13:20:24才保存成功。DEBUG在此区间记录130次模型开始，没有`semantic judge response unavailable`提示；这不代表130条独立陈述，也不能代替审计metadata的最终状态或准确率。

本次未读取账号加密数据库和最终报告正文，不报告supported比例、不声称逐句核验通过；这里只确认日志中的调用推进、保存成功和实际存在的处理缺陷。网页进度可分开显示“引用辅助检查”和“保存”，避免用户把持续检查误认成数据库卡死。

## 范围、产物和后续

监控已跟踪到任务成功结束，没有安装后台常驻监控。未改变运行应用、代理、SearXNG、模型参数或用户任务。未执行整库测试，因为没有应用改动；只做实际安装格式化检查、两次NCBI公开身份核查和文档空白检查。

首要后续：修正文献自身PMC映射及身份核对；保留相关性异常返回的必要诊断并修正常见格式兼容；改进全文正文提取/章节取证和书目信息传递。来源池与同步审计进度另行调整，不以平台关键词或大量题目约束替代这些机制修正。

私有轻量记录位于`/data/ningh/nh/ldr-experiments/web-monitor-20261021-06641267/`，含观测脚本、快照、fetch范围统计、PMC公开核查和实际安装格式化结果；不保存原始完整Docker日志或论文全文。
