# 研究证据与引用模块

本目录安装为独立research_verify包，含当前研究流程、可选辅助审计和旧数据/CLI兼容模块；存在不表示全部启用。当前入口见[研究流程](../../docs/current-research-flow-20261016.md)和[源码布局](../../docs/source-layout.md)。

| 模块 | 当前用途 |
| --- | --- |
| source_collection/source_identity/source_relations/pmc_identity | 来源反馈、稳定身份、显式版本关系及PMC自身身份 |
| subtask_handoff/subtask_research | 研究导航和真实原文交付；第二版有界检索、独立交付及子任务过程保全已测试并于11月5日部署5002，见[实现](../../docs/subtask-handoff-v2-20261104.md)/[部署](../../docs/subtask-handoff-v2-deploy-5002-20261105.md) |
| source_reading | 第三版开发候选的写作前原句/主体/状态阅读和分组；引用存在不代表语义核验，额外一次读取失败时仍保留原材料成文，已部署5002，见[验证](../../docs/subtask-scope-v3-20261105.md) |
| generation/evidence_flow/evidence_fetch | 证据材料、必要引用预留、写后核对、有限补证及独立确认的局部修订 |
| publication/citation_display | 正文/来源映射、首次引用编号、链接、metadata与保存一致性 |
| synthesis_trace | 私有实际输入输出与过程快照 |
| citation_qc/claims/passages等 | 可选保存前逐引用辅助审计，当前实例关闭，不同于写后事实核对 |
| revision/semantics中的旧结构及其他契约/CLI | 历史数据兼容或独立调用，不恢复旧规则删句和硬性发布准入 |

当前事实检查开启时可能在原文定位和独立确认后局部修订实际成文；不能笼统称整个系统不做自动修订。publication本身保留正文、整理引用，关闭/故障不会阻断报告，发布状态不代表核验通过。辅助审计结果在metadata，不追加正文核验表。

原DOI、条件匹配、关键词及严格契约模块仍可独立调用，当前报告主流程不以它们强制准入；JIF/全文/研究条件没有因此获得完成证明。模型语义、跨语言、多来源和证据覆盖仍有限制，见[待办](../../docs/roadmap.md)。
