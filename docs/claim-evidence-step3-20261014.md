# M3-A 第3项：逐篇语义支持核查阶段结果

> 文档定位：历史试验；六维强制结构不再作为门槛。本页记录当时过程；当前状态见[状态总览](current-status.md)，有效后续见[待办](roadmap.md)。

日期：2026-10-14；代码起点：7f885ee；分支：work/ldr-20261012。
状态：当前版本实现、自动回归、真实模型小样本对照和镜像构建导入检查完成。
边界：这不是完整反幻觉或最终报告发布阶段的完成声明。

## 实现

- 新增 semantics.py，要求模型逐篇返回 population、quantities、direction、causality、study_design、scope 六项结构化检查。
- 每项 matched/partial/mismatch 均须有可在实际呈现片段内定位的短引；缺项、非法状态、无法定位的必要依据和不确定判断不会得到 supported。
- 对显式需要的检查项，not_applicable 不能绕过核验；全项不适用也不能作为 supported。
- 规则拦截限定在选中的原文短引：关联表述升级因果、前临床短引支撑人类疗效、单一量值或单位不一致、同一明确终点的方向反转。
- 用 Decimal 归一化已支持的质量和浓度单位，0.005 mg/mL 与5 micrograms/mL可等价；多数量、复杂终点与语境不做数值袋猜测，交给结构化模型检查。
- 支持逐维 partial。顶层模型supported会因有效矛盾降为unsupported、因partial降为partial、因不确定降为unverifiable；明确规则矛盾不能被其他不确定项掩盖。
- 修复 cause-specific mortality / cause of death 名词被误认成因果主张的边界。
- 未主张设计、也未显式升级因果时，方法信息缺失可以记录design_not_asserted；显式因果主张不能跳过设计不确定性。
- CitationSupport保留原模型判定、semantic_schema_version、逐项检查、模型/规则来源、理由及原文定位。既有ClaimCheck顶层接口保留。
- 旧的supported模型回复若不包含六项检查会降为无法核验。旧单测的mock补齐结构化字段，只验证接口与规则，不冒充真实语义模型。

## 自动回归与运行兼容

全量：176 passed（0.54s），在143项基线上新增33项。
覆盖基线N04实际误判回放、伪造维度短引、缺项/非法状态、必要项被跳过、单位换算、不同终点不误判、模型自称supported但维度矛盾、partial/uncertain聚合、cause-specific词义边界。
Python AST和git diff --check通过。
独立镜像 astro-dra:semantic-qc-20261014 构建成功：固定基础digest、五个补丁安装、包语法及CitationQc导入全部通过。
构建导出的manifest list：sha256:464c574424b4373849f84d4fe56d119e5caef196dad21e2f0c4609736b9e1056。
只构建镜像，没有启动或切换生产容器。完整应用请求、研究任务、导出和数据迁移未验收。pip传递依赖仍未全部锁定，构建导入通过不证明全部运行接口兼容。

## 真实模型验证（请求模型标识 deepseek-v4-flash，temperature=0）

| 验证集合 | 完全一致 | 正例supported | 非正例误fully supported |
|---|---|---|---|
| 原15条合成样例最终复跑 | 14/15 | 2/3 | 0/12 |
| 6条明确范围/等价单位正例 | 6/6 | 6/6 | 无负例 |
| 最终组合21条合成样例 | 20/21 | 8/9 | 0/12 |
| 两篇真实论文的6条摘要对照，最终版本 | 6/6 | 3/3 | 0/3 |

原15条中N04从基线错误supported改为unsupported。
保留的差异是P02：结论没有明确“培养细胞”范围，证据仅支持该范围，最终返回partial；原始预置标签仍保持supported，未修改标签来美化一致率。
明确加上培养细胞范围的Q02在最终正例集合中supported。后续报告修订应补充此类范围限定，不能直接删除范围继续发布。
原21条与真实6条合计27条：26条与预置标签一致，15条非正例没有错误完全通过。样本小且标签由工程代理审阅，不是独立领域专家评估，不代表泛化准确率或零幻觉保证。

阶段保留了初版过度拦截、v2、final和最终组合结果，不覆盖或删除不理想的历史数据。
每次新结果记录代码基线、工作区是否有改动、验证包与样例哈希及API返回的模型标识。请求标识不独立证明模型权重身份。
旧结果semantic-pilot-20261014-final.json早于最后的词义修正；当前最终状态以semantic-stage-final-20261014.json和semantic-real-excerpts-20261014-final.json为准。

## 真实论文来源与复核

- PMID33567185，DOI10.1056/NEJMoa2032183：[PubMed](https://pubmed.ncbi.nlm.nih.gov/33567185/)。
- PMID22591295，DOI10.1056/NEJMoa1112010：[PubMed](https://pubmed.ncbi.nlm.nih.gov/22591295/)。

只使用已从PubMed API核对的短摘要片段，每篇保留不超过25词，不声称取得全文。
样例包含源摘要位置、摘要哈希、DOI和PMID；真实模式复跑会再次核实DOI和片段位置一致性。
结果用哈希替代重复原文和模型回复；原文只保留在短引fixture，定位可回放到fixture并映射到摘要。全文和详细研究报告仍需独立验收。
两篇论文的样例标签由工程代理依据短引核对，没有用户或领域专家独立裁决。

## 文件与复跑

- local_deep_research/research_verify/semantics.py：模式、维度依据验证与规则。
- local_deep_research/tests/test_semantic_qc.py：阶段回归。
- local_deep_research/tests/fixtures/semantic_stage_final_cases.json：原样例与明确范围正例。
- local_deep_research/tests/fixtures/real_semantic_excerpt_cases.json：真实来源短引。
- scripts/run_semantic_pilot.py：模型实测；真实短引模式需 --allow-verified-excerpts。
- docs/semantic-stage-final-20261014.json、semantic-real-excerpts-20261014-final.json：最终实测数据。

复跑使用新的输出路径，避免覆盖既有文件。模型配置在内存中读取容器环境，不显示或保存凭据。
单测命令仍为工程基础记录中的pytest命令。

## 后续接续

下一项：统一最终报告正文与保存前发布控制；对partial补齐范围或拆分主张、删除/修订unsupported、明确处理unverifiable，修订后重新核查。
确保普通/详细报告、引用重编号、保存、聊天与导出共享同一核查版本，不能在异常时回退发布原始未核查文本。
还需扩大真实语义样本、独立人工评估和复合结论拆分；当前规则有限，既不能穷尽语义错误，也不能替代全文/出版身份核验。
本次未推送、未部署。提交标题：Add structured semantic evidence checks and validate real-paper excerpts。
