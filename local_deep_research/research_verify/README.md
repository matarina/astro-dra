# research_verify —— 科研验证链（四需求）

本页描述现有标注式核验实现，不能作为严格证据准入的验收证明。严格流程、已知缺口与后续任务见 [工程计划](../../docs/ldr-verification-engineering-plan.md)；通用部署入口见 [项目 README](../../README.md)。下文的旧回滚快照与部分内部依据文件未随仓库提供，请以 [部署说明](../../docs/deployment.md) 为准。

> 在「检索到 → 写报告」之间插入验证，在报告产出后做后置 QC。
> 全部走 hot-patch：新代码集中在 `research_verify/`，入口只改
> `langgraph_agent_strategy.py::_finalize` 一两处，不动上游检索内核。
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
| `citation_qc.py` | 需求4 | 结论↔被引原文支撑三态判定（反幻觉） |
| `cli_check.py` | 3/4 | 离线复核 CLI（拉 PubMed efetch 对账） |

## 状态语义（绝不静默）

- 需求1 `verified`：`True`(已核验) / `False`(无效) / `None`(未能核验，如断网)
- 需求2 `hard_violations`：非空 → 报告标注不符合条件；全不满足 → 显式提示，不放宽凑数
- 需求3 `threshold_ok`：`False` → 标注不达标（basis=abstract 时提示未验证全文）
- 需求4 `verdict`：`supported`/`partial`/`unsupported`(⚠️缺少支撑)/`unverifiable`(未能核对)

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
- `### 结论可溯源性核查`（+ `⚠️缺少支撑` 内联标记；JSON 落盘 `/data/logs/citation_qc_*.json`）

## 回滚

- 开关：`LDR_VERIFY_ENABLE_VERIFY=false` 一键关停。
- 代码：删除 `research_verify/` 新增模块 + 移除 Dockerfile 对应 COPY/RUN。
- 镜像：基线快照 `docker-compose.yml.actdoc_base_20260928`。

## 依据

`LDR-四需求-实施方案.md`、`LDR-四需求-行动文档.md`、`LDR-四需求-详细执行规划.md`。

## 逐引用证据定位（2026-10-12）

CitationQc 已改为逐篇检查，supported/partial 须有程序验证存在的原文短引。新增 evidence.py 和 citation_checks 审计字段；详情见 [阶段记录](../../docs/claim-evidence-step1-20261012.md)。仍使用1500字窗口，全文获取、无引用句检测、严格发布控制和真实模型验收尚未完成。
