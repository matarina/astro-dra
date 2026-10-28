# 引用辅助核查

当前用途：对最终报告中的带引用陈述，使用对应来源片段让模型提出支撑关系判断。保留来源身份、文本哈希和可定位短引，判断存入`research_meta.claim_publication.citation_audit`，不追加到报告正文。

`publish_report`保留生成文本，展示编号按首次引用顺序整理并对同篇去重，以可见`[1]`链接输出。原引用编号保存在`original_indices`及原文审计中。无证据、模型错误、关闭核查均不删句、不阻断输出，也不宣称已核验通过。新发布状态为`unverified`；`audit_status`区分已执行、关闭、不可用和无带引陈述。

已删除自动修订循环、对象/数字/因果/分析名称等正则否决、六维必填判断及策略收尾的条件/关键词/真实性附表。`revision.py`和`semantics.SemanticCheck`仅保留历史JSON读取结构。`CitationQc.render_section`只用于兼容历史报告，正常发布不调用。

原有DOI、条件匹配、关键词和严格契约模块仍可独立调用，当前报告主流程不调用这些准入检查。`enable_constraint_match`与`enable_keyword_coverage`默认关闭。

限制：现有分句与词项检索只作辅助；多引用联合支撑、跨语言检索、全文覆盖、模型误判仍待改进。辅助核查不是可靠的零幻觉证明。后续基于真实样本比较开源方法。

完整流程与验证边界见仓库`docs/current-research-flow-20261016.md`。
