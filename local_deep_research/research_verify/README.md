# research_verify —— 科研验证链（四需求）

结论核验已完成摘要与正文检查的第一轮实现；DOI、条件和关键词模块仍有严格准入缺口，不能据此宣称整篇报告通过全部严格条件。完整验收门槛见 [工程计划](../../docs/ldr-verification-engineering-plan.md)；部署入口见 [项目 README](../../README.md)。下文旧回滚快照与部分内部依据文件未随仓库提供，以 [部署说明](../../docs/deployment.md) 为准。

## 摘要与正文核验第一版

当前流程为：按句和分句提取陈述及表格数据行，逐条逐引用检查摘要支持情况，在同篇正文的窗口中检索证据，校验原文引文位置，复判疑难项，有限改写后再次核验。无引用事实也进入检查；不能核实的陈述从最终正文移除，并在核查记录中说明。仅标题和代码块不做事实陈述抽取；这还不是完整的语义原子事实解析器。

摘要支持比例是本次被核查陈述中得到摘要支持的比例，不是幻觉概率。缺摘要或摘要判定未完成时，比例为 `null`，报告注明未完成，不能解释成低匹配。默认 `qc_require_body=true`，高摘要支持也不能代替正文。低摘要支持不会否决正文中的真实细节；摘要与正文发生明确冲突时保持待核验。

正文使用显式 `body` 字段，或 `content_type=full_text/fulltext/body` 对应的 `full_content/content`。未声明类型的 `full_content` 不按长度推断为正文；标记为摘要、只有摘要、正文与摘要完全相同的内容均不能作为正文通过。已识别的 Abstract 和 References 区段不参与正文检索。正文获取和完整性核实仍依赖上游来源；当前没有新增联网全文下载器，也不等同于完成工程计划 M2。

通过需要模型提供原文短引。程序只接受已发送给模型的窗口内存在的引文，保存原字段、SHA256、起止偏移和原文；只允许空白归一化，不接受模糊相似或翻译文本冒充引文。存在引文不保证模型的语义判断正确，仍需真实样本评估。

每个引用独立判定，不能让一篇支持掩盖另一篇错引。复杂的跨文献联合论证目前采用保守策略；无法由各被引论文分别支撑的复合陈述可能被移除。默认使用现有模型进行分开的复判调用，可在策略实例上注入 `citation_review_model`；本次没有安装专用判定模型。

正文不通过时，仅在已有可定位正文证据允许的情况下提出缩小或更正后的表述；改写必须保留允许的引用，随后重新核查。超过预算、模型异常、伪造引文及改写失败均不能回退发布原句。旧 Sources 和核查附录会先移除，避免未检查内容留在跳过的区段。

LangGraph 的 `findings.content`、`current_knowledge`、`final_report.content` 共用修订后的正文，`formatted_findings` 在此基础上附加来源。服务优先读取 `final_report`；详细报告在整合后、引用重新编号和保存前再核验一次。API 的 `final_report.verification`、审计 JSON 和保存元数据记录结果。`scope=claim_grounding_only` 表示结论证据核验，不代表 JIF 等其他条件通过。

`content_sha256` 对应核验后的正文，`rendered_content_sha256` 对应附加核查表后的版本，保存时另记 `saved_content_sha256`。来源引文偏移始终对应记录中哈希确定的原字段；核验时引用编号早于展示时的引用重编号。

### 预算配置

根目录 `.env.example` 和 Compose 已传递以下配置，均带 `LDR_VERIFY_` 前缀。默认每份报告最多评估 80 条陈述、调用模型 200 次，每条疑难来源最多复判 1 次、每条可修复陈述最多改写 1 次。摘要、正文、复判和改写共享调用预算，超出限制的结论标记待核验并移除，不静默跳过。

| 后缀 | 默认值 | 作用 |
| --- | --- | --- |
| `ENABLE_CITATION_QC` | `true` | 结论核验开关；关闭后状态为 `disabled` |
| `QC_REQUIRE_BODY` | `true` | 是否必须有正文证据；显式关闭时仅摘要通过会标注其范围 |
| `QC_MAX_CLAIMS` | `80` | 首次检查与修订检查共享的陈述预算 |
| `QC_MAX_MODEL_CALLS` | `200` | 每份报告的模型调用预算 |
| `QC_REVIEW_ROUNDS` | `1` | 疑难来源复判上限，范围 0 至 2 |
| `QC_REPAIR_ROUNDS` | `1` | 单条陈述改写上限，范围 0 至 2 |
| `QC_CONTEXT_CHARS` | `6000` | 每次发送的证据字符预算 |
| `QC_CHUNK_CHARS` | `1200` | 正文窗口大小 |
| `QC_TOP_K` | `4` | 每次检索窗口数上限 |

这些是单份报告的预算；详细报告的章节研究和最终整合会分别核验。远程模型调用的超时继续由既有模型客户端控制。缺少正文时输出会更保守；模型效果、跨语种检索召回及实际延迟需要联网试点验证。

> 在「检索到 → 写报告」之间插入验证，在报告产出后做后置 QC。
> 代码通过 hot-patch 安装：核验逻辑集中在 `research_verify/`，
> 在策略终结和服务保存位置接入，不重写上游检索内核。
>
> 设计契约：**校验 = 标注 / 剔除 / 留痕**，绝不静默通过、也绝不让整篇失败。
> 断网自动降级为 `unverified` 留痕，不阻塞主流程。

## 模块

| 文件 | 需求 | 说明 |
|------|------|------|
| `config.py` | — | `VerifyConfig`（`LDR_VERIFY_*` 总开关 + 各模块开关 + 阈值） |
| `http_client.py` | — | 共享异步 HTTP（信号量限流、重试、ok/not_found/transport_error 三态） |
| `models.py` | — | 全部 pydantic 模型（`VerifyResult`/`ResearchConstraint`/`KeywordCov`/`ClaimCheck`…） |
| `textutil.py` | — | 纯函数工具（标题/年份/DOI/PMID 归一化） |
| `doi_validator.py` | 需求1 | Crossref/PubMed 在线校验 DOI/PMID 真实性 |
| `constraint_matcher.py` | 需求2 | 年份/IF/语种硬约束匹配（IF 走 journal_quality，`0.0` 视为未知） |
| `keyword_cov.py` | 需求3 | 全文/摘要关键词命中覆盖 |
| `evidence.py` | 需求4 | 证据类型、全文窗口检索、逐篇引用查找和原文偏移校验 |
| `citation_qc.py` | 需求4 | 摘要与正文支持判定、复判、有限修订、统一正文及审计 |
| `cli_check.py` | 3/4 | 离线复核 CLI（拉 PubMed efetch 对账） |

## 状态语义（绝不静默）

- 需求1 `verified`：`True`(已核验) / `False`(无效) / `None`(未能核验，如断网)
- 需求2 `hard_violations`：非空 → 报告标注不符合条件；全不满足 → 显式提示，不放宽凑数
- 需求3 `threshold_ok`：`False` → 标注不达标（basis=abstract 时提示未验证全文）
- 需求4 `verdict`：`supported`/`partial`/`unsupported`/`contradicted`/`unverifiable`。摘要证据不足与原文明示相反分别处理；只有满足当前证据规则的陈述保留。

## 开关（docker-compose env）

```
LDR_VERIFY_ENABLE_VERIFY=true            # 总开关，false 全链短路
LDR_VERIFY_ENABLE_DOI_VALIDATION=true
LDR_VERIFY_ENABLE_CONSTRAINT_MATCH=true
LDR_VERIFY_ENABLE_KEYWORD_COVERAGE=true
LDR_VERIFY_ENABLE_CITATION_QC=true
LDR_VERIFY_MIN_KEYWORD_HITS=3
LDR_VERIFY_KEYWORD_THRESHOLD_RATIO=0.75
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

# 离线复核（需求3/4）
docker exec <container> /install/.venv/bin/python -m research_verify.cli_check --pmids 32561899 --keywords "m6A,METTL3" --threshold 2

# 单测（容器未装 pytest；本地 venv 或临时装）
pytest -q tests/
```

## 报告产出

`_finalize` 在报告末尾按需追加小节（有数据才出现）：

- `### 文献真实性核验`
- `### 条件匹配核验` / `### 条件匹配提示`（全不满足时）
- `### 关键词覆盖核验`
- `### 摘要支持情况`、`### 结论可溯源性核查`。不通过的陈述已从研究正文移除，表中保留判定与修改原因；JSON 落盘 `/data/logs/citation_qc_*.json`，格式为带 `policy_version` 的审计对象。

## 回滚

- 开关：`LDR_VERIFY_ENABLE_VERIFY=false` 一键关停。
- 代码：删除 `research_verify/` 新增模块 + 移除 Dockerfile 对应 COPY/RUN。
- 镜像：基线快照 `docker-compose.yml.actdoc_base_20260928`。

## 依据

`LDR-四需求-实施方案.md`、`LDR-四需求-行动文档.md`、`LDR-四需求-详细执行规划.md`。
