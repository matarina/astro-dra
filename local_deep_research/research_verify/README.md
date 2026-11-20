# research_verify —— 来源身份与事实一致性辅助链

[Markdown角色/引用候选（2026-11-11）](../../docs/markdown-citations-20261111.md)把新报告的引用语法与科学分类分开：CommonMark结构定位code/link/reference，普通heading/question/advice保持unknown candidate，不由科学词表决定。修复Detailed Findings藏引用与URL拆句；新保存格式2.2，2.0/2.1旧记录继续用冻结兼容路径，不迁移历史报告。24/24安装syntax/routing契约和31新增检查不证明科学效果；扩展套件229绿/37共享红，实际Quarto URL导出检查两臂均失败。保存QC仍关，原生一致性保持开启；本候选未部署。医学full-text新参考池已封存但span合同仍待核对，尚未改变选材。

## 当前开发候选：显式意图与未知状态（2026-11-10）

未部署候选停止从问题关键词推断出版语言/年份、论文数量、字段或报告模式；原问题仍交给Agent/Writer。`report.*`显式设置经校验后带provenance，缺失/冲突值保持unknown或pending，不创建科学条件通过或发布门槛。ConstraintMatcher不再自动调模型猜条件。保存前QC仍关闭，LDR原生事实一致性保持开启。

见[候选与真实配对评测](../../docs/structured-intent-candidate-20261110.md)。32份纠正材料的生成完成，但12份辅助标注无效且存在judge与来源复读分歧；不宣称总体幻觉下降或跨域稳健性通过。下面旧需求/CLI术语仅作模块背景，不代表当前自动准入策略。

后续[元数据未知状态候选](../../docs/metadata-unknowns-20261110.md)进一步区分缺adapter字段与论文未报告：card用`unknown`/`missing_metadata`，提供值用`provided_metadata`并记录原key。物种/队列/n/仪器/方法/出版类型不自动变成人群/分组/样本量/平台/技术/研究设计，原字段仍供native reader读取。预印本来源不自动断言未同行评议；显式布尔值只是带provenance的metadata assertion，未独立核实。9真实记录/5合成契约只验证安装组件与信息保全，未部署、未进入此前报告级对照，不证明报告改善。下文历史`not reported`描述不能当作此候选的未知状态语义。

[旧引用来源恢复候选](../../docs/source-recovery-20261111.md)修复refetch重复来源在reset后不回到当前调用，以及finalize没有新来源时跳过草稿显式引用的旧来源。仅按既有数字引用语法恢复唯一记录，保留所有当前来源、缺失/歧义标签和archive，不扩整个历史来源池。`source_recovery.scope=citation_index_lookup_only`不是科学核验。实际安装16项组件probe与90项集中测试不等于native模型报告质量通过；旧报告级对照不覆盖这个候选。

[API记录身份候选](../../docs/identity-provenance-20261111.md)由实际返回记录保留provider/ID/title/types/hash并绑定本地元数据；URL、旧verified布尔值和generic warning不足以确认/否定身份。Crossref 404仅该registry未找到，空/错ID响应保持unknown；预印本身份、indexed/registered state、文献类型与同行评议独立。Receipt不是密码学认证，也不证明正文支撑。17 adapter观察仅9条已读记录，完整摘要/ID/URL保全；117集中检查通过，扩展套件另有25项两臂共享失败，不能报全绿。未部署且无新模型报告评估，总体效果未证明。

当前生产方向以生物医学文献检索和有用报告为主。来源身份、正文准备和事实一致性只提供可见状态与证据上下文；保存前逐引用 QC 默认关闭，不构成发布门槛。旧严格工程计划仅作历史参考。

## 摘要与正文核验第一版

当前生产流程为：保留检索材料，规范化来源身份，准备摘要/正文和逐篇 evidence card，再把来源状态与范围契约交给写作模型。缺失字段显示为 `not reported in the supplied material`；来源不明、预印本、非文献页面和冲突身份保留为带状态的线索，不静默删除。仅标题和代码块不做事实陈述抽取；这还不是完整的语义原子事实解析器。

来源状态按正交字段保存：稳定身份、`document_type`、`publication_state`、`peer_review_status`、`relevance_status`、证据范围、时间有效性和冲突状态。`formal` 只说明权威记录身份成立，不等同于研究论文、同行评审、相关性或用户条件已满足；缺失信息保持 `unknown`。

摘要支持比例是本次被核查陈述中得到摘要支持的比例，不是幻觉概率。缺摘要或摘要判定未完成时，比例为 `null`，报告注明未完成，不能解释成低匹配。默认 `qc_require_body=true`，高摘要支持也不能代替正文。低摘要支持不会否决正文中的真实细节；摘要与正文发生明确冲突时保持待核验。

正文使用显式 `body` 字段，或 `content_type=full_text/fulltext/body` 对应的 `full_content/content`。未声明类型的 `full_content` 不按长度推断为正文；正文获取失败会保留缺口并继续报告。已识别的 Abstract 和 References 区段不参与正文检索；这不等同于旧工程计划的严格准入通过。

通过需要模型提供原文短引。程序只接受已发送给模型的窗口内存在的引文，保存原字段、SHA256、起止偏移和原文；只允许空白归一化，不接受模糊相似或翻译文本冒充引文。存在引文不保证模型的语义判断正确，仍需真实样本评估。

来源状态和身份仍按篇记录，不能让一篇论文掩盖另一篇错引。复杂的跨文献联合论证标为待核验；可选诊断运行时可以生成旁路检查，但不会改写或扣留生产正文。

超过预算、模型异常或正文不可取时，状态写入材料元数据，报告仍保留可用内容和明确缺口。生产路径不插入正文核验表，也不以“未核验”替换原报告。

LangGraph 的 `findings.content`、`current_knowledge`、`final_report.content` 共用修订后的正文，`formatted_findings` 在此基础上附加来源。服务优先读取 `final_report`；详细报告在整合后、引用重新编号和保存前再核验一次。API 的 `final_report.verification`、审计 JSON 和保存元数据记录结果。`scope=claim_grounding_only` 表示结论证据核验，不代表 JIF 等其他条件通过。

`content_sha256` 对应生成正文，来源引文偏移对应记录中哈希确定的原字段；展示时再进行引用重编号。可选诊断的审计 JSON 为旁路产物，不授权删除正文。

### 预算配置

根目录 `.env.example` 和 Compose 已传递以下配置，均带 `LDR_VERIFY_` 前缀。逐引用 QC 默认关闭；以下预算仅供显式诊断使用，不是生产报告门槛。

| 后缀 | 默认值 | 作用 |
| --- | --- | --- |
| `ENABLE_CITATION_QC` | `false` | 可选诊断开关；生产默认关闭 |
| `QC_REQUIRE_BODY` | `true` | 是否必须有正文证据；显式关闭时仅摘要通过会标注其范围 |
| `QC_MAX_CLAIMS` | `80` | 首次检查与修订检查共享的陈述预算 |
| `QC_MAX_MODEL_CALLS` | `200` | 每份报告的模型调用预算 |
| `QC_REVIEW_ROUNDS` | `1` | 疑难来源复判上限，范围 0 至 2 |
| `QC_REPAIR_ROUNDS` | `1` | 单条陈述改写上限，范围 0 至 2 |
| `QC_CONTEXT_CHARS` | `6000` | 每次发送的证据字符预算 |
| `QC_CHUNK_CHARS` | `1200` | 正文窗口大小 |
| `QC_TOP_K` | `4` | 每次检索窗口数上限 |

这些是单份报告的预算；详细报告的章节研究和最终整合会分别核验。远程模型调用的超时继续由既有模型客户端控制。缺少正文时输出会更保守；模型效果、跨语种检索召回及实际延迟需要联网试点验证。

> 在「检索到 → 写报告」之间准备来源身份和证据上下文；逐引用 QC 仅作为可选诊断。
> 代码通过 hot-patch 安装：核验逻辑集中在 `research_verify/`，
> 在策略终结和服务保存位置接入，不重写上游检索内核。
>
> 当前设计契约：**身份与证据 = 标注 / 保留 / 留痕**，不自动删除、不设置硬发布门槛。
> 断网自动降级为 `unverified` 留痕，不阻塞主流程。

## 模块

| 文件 | 需求 | 说明 |
|------|------|------|
| `config.py` | — | `VerifyConfig`（`LDR_VERIFY_*` 总开关 + 各模块开关 + 阈值） |
| `http_client.py` | — | 共享异步 HTTP（信号量限流、重试、ok/not_found/transport_error 三态） |
| `models.py` | — | 全部 pydantic 模型（`VerifyResult`/`ResearchConstraint`/`ClaimCheck`…） |
| `textutil.py` | — | 纯函数工具（标题/年份/DOI/PMID 归一化） |
| `doi_validator.py` | 需求1 | Crossref/PubMed 在线校验 DOI/PMID 真实性 |
| `constraint_matcher.py` | 需求2 | 年份/IF/语种范围提示（IF 走 journal_quality，`0.0` 视为未知；不删除来源） |
| `evidence.py` | 需求4 | 证据类型、全文窗口检索、逐篇引用查找和原文偏移校验 |
| `citation_qc.py` | 需求4 | 摘要与正文支持判定、复判、有限修订、统一正文及审计 |

## 状态语义（绝不静默）

- 当前开发候选 `verified`：`True`仅表示provider返回请求的ID；`None`包括registry未收录、空/错误/不匹配响应和断网。旧`False`不能在缺scope/provenance时当全球无效；标题/年份一致性、同行评议与科学支撑另行表示。
- 需求2 `hard_violations`：仅作为范围提示；来源仍保留，不阻止报告
- 需求4 `verdict`：`supported`/`partial`/`unsupported`/`contradicted`/`unverifiable`。诊断结果写入旁路元数据，不替换生产正文。

## 开关（docker-compose env）

```
LDR_VERIFY_ENABLE_VERIFY=true            # 总开关，false 全链短路
LDR_VERIFY_ENABLE_DOI_VALIDATION=true
LDR_VERIFY_ENABLE_CONSTRAINT_MATCH=true
LDR_VERIFY_ENABLE_CITATION_QC=false
LDR_VERIFY_CROSSREF_MAILTO=<mailto>
```

## 自测 / 验收

```bash
# 包自测（配置 + Crossref 可达性）
docker exec <container> /install/.venv/bin/python -m research_verify

# 需求1 验收 1a/1b/1c
docker exec <container> /install/.venv/bin/python -m research_verify.doi_validator --doi 10.1038/s41586-020-2649-2
docker exec <container> /install/.venv/bin/python -m research_verify.doi_validator --doi 10.9999/does-not-exist-xyz123
docker exec <container> /install/.venv/bin/python -m research_verify.doi_validator --doi 10.1038/s41586-020-2649-2 --wrong-title "Wrong"

# 单测（容器未装 pytest；本地 venv 或临时装）
pytest -q tests/
```

## 报告产出

生产 `_finalize` 保留正文，并在书目中显示来源状态；范围、身份和可选事实一致性结果只写入 trace/metadata，不追加正文核验表。可选诊断才会生成 `citation_qc_*.json`；其中的判定不授权删除或扣留正文。

## 回滚

- 开关：`LDR_VERIFY_ENABLE_VERIFY=false` 一键关停。
- 代码：删除 `research_verify/` 新增模块 + 移除 Dockerfile 对应 COPY/RUN。
- 镜像：基线快照 `docker-compose.yml.actdoc_base_20260928`。

## 依据

`LDR-四需求-实施方案.md`、`LDR-四需求-行动文档.md`、`LDR-四需求-详细执行规划.md`。
