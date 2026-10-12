# M3-A 第1项：逐引用映射与原文短引定位

日期：2026-10-12；代码起点：6a5eae8；分支：work/ldr-20261012。
状态：代码、确定性回归与策略入口接口验证完成；未部署，未执行真实模型研究验收。

## 实现行为

- CitationQc 通过 collector.find_by_index 为每个引用独立解析文献，拒绝编号不一致、缺失来源与已知身份错配。
- 优先 DOI、PMID，随后 URL 哈希或明确 paper_id 作为稳定身份；引用重编号不改变 paper_id 或原文 artifact ID。
- evidence.py 将来源字段转换为不可变内存文本 artifact，保存原始文本 SHA-256；字符位置和短引对应该原始字段。
- 每篇引用独立调用已有判卷模型，不再把多篇文献片段合并掩盖错配；保留逐篇 outcome。
- 模型返回 supported 或 partial 必须给出可在该篇文本中定位的连续短引，且短引必须处于实际送入模型的文本范围。
- 匹配容许空白/换行差异，但不改变大小写、标点、数字、否定词、方向或省略文字。审计保存原始短引与 start/end。
- 依据 content_type 区分 fulltext/abstract；没有明确原文类型的字段保守标为 snippet，不能仅凭字段名或长度标全文。
- snippet 可定位，但不能因此得到原文已证实的 supported/partial，返回 original_text_unconfirmed。
- 全部被引文献均 supported 才返回整体 supported；任何 unverifiable 不会被其他篇的 supported 掩盖。
- ClaimCheck 增加 claim_id 和 citation_checks，旧顶层字段保留；每篇含来源、依据、原文字段版本、评估长度、理由和 ClaimEvidence。
- 报告核查表展示逐篇短引和字符位置；策略现有 model_dump JSON 审计可携带新字段，未修改部署补丁安装清单。
- 缺少直接网址时从 DOI/PMID 生成 resolver 链接；生成链接不代表本次已在线验证可打开。

## 验证证据

命令：

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=local_deep_research /data/ningh/nh/verify-venv/bin/python -m pytest -q -p no:cacheprovider local_deep_research/tests

最终：109 passed（0.42s），在77项基线上新增32项。
覆盖：伪造/改写/空短引、数字和否定词变更、空白映射、位置哈希、摘要冒充全文、片段误通过、缺失第二篇、逐篇模型输入隔离、全部引用通过、错编号/已知DOI错配、来源缺文本/身份、重编号、重复引用、JSON回放、错误模型类型、窗口外短引、resolver 链接。
策略接口测试执行实际 SearchResultsCollector 类与 _attach_citation_qc 方法，隔离缺失的完整应用依赖；确认新审计结构能够传入返回值与 JSON 序列化。它不是容器或完整研究流程验收。
修改 Python 文件 AST 校验及 git diff --check 均通过。

## 当前边界与后续任务

1. 仍沿用已有判卷模型和1500字窗口；下一项实现相关证据段落检索及无引用事实句覆盖。
2. 只验证模型短引在指定来源文本中的存在性；语义是否真实支持主张仍由原有模型判断，后续单独评估对象、数值、研究类型和因果强度。
3. 来源全文类型依赖获取器标签，尚无独立全文完整性或出版身份验收；本次不证明 DOI、年份/JIF/语种或正文关键词条件。
4. 不自动获取缺失原文；定位缺少页码/章节时只记录字符区间，不编造页码。正文 artifact 为内存快照，尚未持久化完整文本；复核需同字段同哈希版本原文。
5. 无引用句检测、修订/删除和最终报告发布控制尚未实现。当前未核验或不支持的正文仍可能保留，不能视为完整反幻觉交付。
6. 普通/详细报告的统一保存出口和引用重编号审计映射属于后续任务；审计中的编号为当前 collector 编号，稳定 paper_id 才是跨编号依据。
7. 未真实在线核验文献、未运行真实模型、未重建镜像或切换生产；未推送。
8. 新的逐篇调用次数随引用关系增加，需后续测量和配置总任务预算。

提交标题：Verify per-citation source mapping and verbatim evidence quotes。
