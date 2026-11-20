# 当前研究流程

更新：2026-11-06。保留旧文件名以兼容既有入口；本正文描述当前固定运行镜像加补丁的流程。[原始历史正文](research-flow-history-20261104.md)与[main历史补充](research-flow-main-history-20261104.md)保留当时的时间线。实例及开关见[当前状态](current-status.md)。

## 从提问到报告

下述描述5002当前第三版（11月5日13:48:57部署）。11月6日已合入main并部署5000，两实例均具备该子任务交付与原文阅读；[5000部署](deploy-main-5000-20261106.md)。见[第三版实现](subtask-scope-v3-20261105.md)和[部署测试](subtask-scope-v3-deploy-5002-20261105.md)。

1. 用户提交问题、普通/详细模式。Flask请求校验账号及角色，读取设置快照并启动后台研究。5002普通用户使用服务端默认/环境配置，管理员保留高级配置；5000已安装新角色，原32账号为普通用户，独立root另建。
2. 默认LangGraph Agent拆分任务、调用搜索/抓取及子研究工具。来源池为PubMed、SearXNG、Europe PMC，默认web_search连接SearXNG；由Agent按需选择，不是固定三源全查。
   5002子任务交付分为研究导航和原文材料：模型选择关键来源，程序从实际收集文本定位/复制并附出处和范围；主任务用导航组织内容，用原文材料写具体事实。默认最多7轮搜索后关闭工具，必要时独立调用一次交付模型；自然完成直接复用作业，异常仍保全消息和当前子任务取得的材料，交付失败返回原文及partial。短摘要完整保留，长文带上下文；模型引句不连续时可按唯一长原文字串恢复同源窗口，保持未定位标记。导航缺口改为当前子任务范围的可选待查问题，未定位或预算省略明确标记，不作为语义已通过。见[第二版实现](subtask-handoff-v2-20261104.md)和[11月5日部署](subtask-handoff-v2-deploy-5002-20261105.md)。
3. 检索结果经过相关性处理、稳定身份去重及来源登记。常规预算500；重复命中可复用编号并回传证据。PubMed/Europe PMC保留元数据与摘要，网页或学术抓取尽量保全实际文本；默认不自动获取每篇PubMed全文。
4. 来源携带编号、标题、URL、DOI/PMID/PMCID、期刊、日期、出版类型及摘要/正文范围。来源身份和明确版本关系可有限补齐；冲突标识、不同版本文本不因标题相似而合并。
5. 写作前优先保留草稿已引用的真实材料。约20万字符来源预算内提供完整摘要/相关原文窗口，必要时批次选材或分章节写作。草稿用于组织，不作为论文证据。5002传入实际摘要/正文窗口阅读范围；明确标注的草稿解读另作待查问题，普通正文和表格保留，原草稿写入trace。每写作批先独立调用一次模型，仅从实际供应的来源选择连续原句及其原文主体/状态（最多24来源、24000引句字符），程序定位原句后按原文主体分组，提醒不混淆不同主体。原文、出处和阅读边界同时交给Writer；读取失败仍提供原文继续成文。该步骤不是语义核验，默认增加一次模型调用。
6. writer生成实际成文。事实检查开启时，对成文按论断分组，传入章节、段落引用范围、表格与原材料，核对研究对象、输入、方法、数量及结论。缺证时有限补取；修订需唯一定位、原文引句确实存在及独立确认，并保留表格结构。未决或调用失败仍保留报告及未决记录。
7. 普通报告经research_service，详细报告经report_generator汇总章节，定时路径复用相应保存入口。统一publication处理首次引用顺序、同篇书目、链接及原编号metadata。保存前单独逐引用QC当前关闭；它与第6步不是同一个开关。
8. 正文与metadata保存到账号数据库/相应存储；展示装配和导出复用映射。publication的一致性检查不表示语义审核通过，当前新发布状态为unverified，不追加旧的四类核验表。
9. 工具返回、来源快照、实际写作材料、核对/补证/修订和publication前后按任务写入私有trace，位于`/data/research_traces`，不附在报告正文。5002另记录每个子任务的提示、AI/Tool消息及交付材料/位置/SHA，沿用私有权限、脱敏与容量状态。

## 对应代码

| 环节 | 部署源码 |
| --- | --- |
| 请求后的研究协调、保存与导出 | `local_deep_research/research_service.py` |
| Agent、子任务和收集器 | `local_deep_research/langgraph_agent_strategy.py`，`research_verify/subtask_handoff.py`、`subtask_research.py`、`source_collection.py` |
| 检索与学术内容获取 | `search_engine_pubmed.py`，`overlay/search_engine_europepmc.py`，`overlay/fetch_tools.py`，`overlay/pubmed_downloader.py` |
| 材料构建、写后核对、补证及身份/版本 | `research_verify/generation.py`、`source_reading.py`、`evidence_flow.py`、`evidence_fetch.py`、`source_identity.py`、`source_relations.py` |
| 引用呈现、保存装配 | `research_verify/publication.py`、`citation_display.py`及`overlay/`下存储/装配模块 |
| 详细模式 | `overlay/report_generator.py` |
| 角色与服务参数控制（5002） | `local_deep_research/astro_accounts/`，`deployment/install_accounts.py` |

以上research_verify路径均相对`local_deep_research/`。完整安装边界见[源码布局](source-layout.md)。

## 当前边界

引用映射正确不保证陈述正确，提供原文也不能保证模型理解正确；核对与确认仍可能漏检/误判。全文、选文条件、论文全集覆盖与跨主题准确率未全面验收。普通/详细/定时有实现与既往流程记录，不表示最新全部改动已做全面质量验收。

旧DOI/条件CLI和历史契约仍有保留，但不作为当前强制准入链；不恢复规则删句、硬性发布门槛或核查失败即拒绝报告。有效待办见[roadmap](roadmap.md)。
