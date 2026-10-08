# LDR 四需求 —— 详细执行规划（实现级）

> 定位：`实施方案.md`（技术选型+接口草案）与 `行动文档.md`（勾选清单）给出的是**需求与验收**。
> 本文件把它们落成**实现级规划**：每个任务的**精确文件、函数签名、数据结构、穿凿点行号、渲染格式、测试用例、验收命令、回滚**。
> 执行方式：严格按 §1→§5 顺序推进，每完成一个任务即：**改代码 → Dockerfile 接入 → 容器内自测 → 验收用例 → 勾选行动文档**。
>
> ⚠️ 本文件是执行依据；若与实施方案/行动文档冲突，以本文件为准，并回写修正上游文档。

---

## 0. 工程约定（所有任务通用，先立规矩）

### 0.1 改造链路（唯一正确姿势）
```
改 nh/local_deep_research/research_verify/*.py
        ↓
docker compose up -d --build          # Dockerfile COPY 进镜像 venv
        ↓
docker logs ... 检查 AST/import 无报错 + 容器 healthy
        ↓
docker exec ... python -m research_verify.<module>   # 容器内自测
```

### 0.2 硬性工程约束（违反即返工）
1. **不阻塞主流程**：所有校验函数必须 `try/except` 兜底；异常 → 记 `unverified` + loguru warning，绝不让研究失败。
2. **绝不静默**：`verified/invalid/unverified`、`supported/partial/unsupported/unverifiable` 三/四态必须显式写回 source，并在报告可见。
3. **可开关**：每个模块读取 `get_config().module_enabled("<name>")`，关掉即完全短路（返回 None，不影响原逻辑）。
4. **去重后校验**：只在 `collector._results`（已去重）上跑，不在原始批次上跑。
5. **并发限流**：外网 I/O 一律走 `HttpClient`（内部信号量），不裸调 httpx。
6. **不改上游检索引擎**：只新增 `research_verify/` + 改 `_finalize` 一处 + Dockerfile/compose。
7. **Python 3.14 / pydantic v2 / fastapi 0.136 不升**。
8. **所有 `.py` 必须能被 Dockerfile 的 AST 校验通过**（无语法错误，import 不触发外网）。

### 0.3 断言与错误码
- 统一 `VerifyResult.verified: bool | None`（`None` = unverified）。
- 需求 2/3 的剔除只在**硬约束**场景生效；软约束只打标。

### 0.4 验收样例（所有任务共用，写入 fixtures）
| 类型 | 样例 |
|------|------|
| 已知真实 DOI | `10.1038/s41586-020-2649-2`（Nature/NumPy） |
| 已知真实 PMID | `32561899`（与上同一篇） |
| 伪造 DOI | `10.9999/does-not-exist-xyz123` |
| 元数据不符 | 真实 DOI + 错误 title |
| IF>=10 真期刊 | `Nature`（17.18）、`Cell`（37.23） |
| IF==0 陷阱期刊 | `Science`、`Nature Medicine` |

### 0.5 回滚
- 代码：`git` 未跟踪文件，删除 `research_verify/<新模块>.py` 即回退。
- 镜像：`docker-compose.yml.actdoc_base_20260928` 快照 + 移除 Dockerfile 对应 COPY 行即可重建。
- 开关：`LDR_VERIFY_ENABLE_VERIFY=false` 一键关停全链。

---

## 1. 任务总览（按序执行，可独立验收）

| 序 | 任务 | 交付文件 | 穿凿点 | 验收 | 预估 |
|----|------|---------|--------|------|------|
| T0 | 共享模型 & 工具 | `research_verify/models.py`、`research_verify/textutil.py` | 无 | 单测 | 0.5d |
| T1 | 需求1 文献真实性 | `research_verify/doi_validator.py` | `_finalize` 收集后 | 1a/1b/1c | 1–1.5d |
| T2 | 需求2 条件匹配 | `research_verify/constraint_matcher.py` | `_finalize` 候选进报告前 | 2a/2b/2c | 1–1.5d |
| T3 | 需求3 关键词覆盖 | `research_verify/keyword_cov.py`、`cli_check.py` | `_finalize` 入选文献 | 3a/3b | 1–1.5d |
| T4 | 需求4 结论可溯源 | `research_verify/citation_qc.py` | `_finalize` 响应前 | 4a–4d | 1.5–2.5d |
| T5 | 联调收尾 | README/测试/演练 | — | §5 | 1–1.5d |

> 说明：行动文档把 T0 归入"基建(已完成)"，但基建只交付了 config/http_client。实现模块前仍需 T0 的共享模型与文本工具，故单列。

---

## 2. T0 —— 共享模型与文本工具（地基补全）

### 2.1 `research_verify/models.py`
集中所有 pydantic 模型，避免循环依赖。

```python
from pydantic import BaseModel, Field

class VerifyResult(BaseModel):
    doi: str | None = None
    pmid: str | None = None
    verified: bool | None = None          # True/False/None(unverified)
    source: str = "unavailable"           # crossref|pubmed|drugbank...|unavailable
    title_ok: bool | None = None
    year_ok: bool | None = None
    warnings: list[str] = Field(default_factory=list)
    verified_at: str = ""                 # ISO8601 UTC

class ResearchConstraint(BaseModel):
    year_from: int | None = None
    year_to: int | None = None
    min_if: float | None = None
    language: str | None = None
    is_hard_default: bool = True

class ConstraintMatch(BaseModel):
    year_ok: bool | None = None
    if_ok: bool | None = None
    lang_ok: bool | None = None
    hard_violations: list[str] = Field(default_factory=list)
    if_unknown: bool = False
    detail: dict = Field(default_factory=dict)

class KeywordCov(BaseModel):
    total: int = 0
    hits: list[str] = Field(default_factory=list)
    missed: list[str] = Field(default_factory=list)
    coverage: float = 0.0
    threshold_ok: bool = True
    basis: str = "unavailable"            # fulltext|abstract|unavailable

class ClaimCheck(BaseModel):
    claim: str
    citations: list[int] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    verdict: str = "unverifiable"         # supported|partial|unsupported|unverifiable
    supporting_fragment: str | None = None
    reason: str = ""
```

### 2.2 `research_verify/textutil.py`
- `normalize_title(s)`：casefold + 去标点（与 collector `_identity_keys` 同口径）。
- `normalize_year(v)`：从 `year|published|publication_date|pubdate` 抽 4 位年份。
- `extract_dois(text)` / `extract_pmids(text)`：复用正则（doi `10.\d{4,9}/...`，pmid `\b\d{7,9}\b`）。
- `first_nonempty(d, keys)`。
- `now_iso()`。

### 2.3 验收
- `python -m research_verify` 扩展为打印 models 可实例化。
- 单测：归一化对齐 collector 口径、年份抽取、DOI/PMID 抽取正负例。

---

## 3. T1 —— 需求 1：文献真实性（DOI/PMID 在线校验）

### 3.1 文件与接口 `research_verify/doi_validator.py`
```python
class DoiValidator:
    def __init__(self, http: HttpClient, cfg: VerifyConfig | None = None): ...
    async def verify(self, source: dict) -> VerifyResult: ...
    async def verify_many(self, sources: list[dict], concurrency: int = 8) -> dict[int, VerifyResult]: ...
```

### 3.2 逻辑（严格按序）
1. 若 `not cfg.module_enabled("doi_validation")` → 返回空 dict。
2. 对每个 source：
   a. 抽 `doi`（`source["doi"]` 或从 link 归一）；抽 `pmid`（`source["pmid"]` / `source["_pmid"]`）。
   b. 有 doi → `GET https://api.crossref.org/works/{doi}?mailto={cfg.crossref_mailto}`
      - `res.ok and res.json["message"].get("title")` ⇒ `verified=True, source="crossref"`。
      - `res.not_found` ⇒ `verified=False, source="crossref"`。
      - `res.transport_error` ⇒ `verified=None, source="unavailable"`。
      - 200 拿 title/year 与 source 比对：不一致 → `warnings += ["metadata_mismatch:..."]`、`title_ok=False`/`year_ok=False`。
   c. 无 doi 有 pmid → `GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={pmid}&retmode=json`；`result[pmid]` 非空且非 `"error"` ⇒ `verified=True, source="pubmed"`。
   d. 都无 → 若 link 命中 `pubmed.ncbi.nlm.nih.gov|doi.org|ncbi.nlm.nih.gov/pmc` ⇒ `source="link"`, `verified=None`（仅标注可解析入口）；否则 `verified=None, source="unavailable"`。
3. `verify_many` 用 `asyncio.gather` + 外层 `HttpClient` 信号量（不再自建并发），返回 `{index: VerifyResult}`。

### 3.3 渲染格式（写入 source + 报告）
- 在 source dict 写 `source["_verify"] = result.model_dump()` 与 `source["_verify_badge"]`：
  - `verified is True` → `✅已核验`
  - `verified is False` → `❌无效DOI`
  - `warnings` 非空 → `⚠️信息不一致`
  - `verified is None` → `❓未能核验`
- 报告末尾追加小节：
```
### 文献真实性核验
| # | 标题 | 状态 | 来源 | 备注 |
|---|------|------|------|------|
| 3 | xxx | ✅已核验 | crossref | |
| 7 | yyy | ❌无效DOI | crossref | 不存在 |
```
- `invalid` 项在正文引用后加 `❌` 标注（不物理删除正文，避免破坏 [N] 编号；Sources 表中剔除或标红由实现选择：**保留编号、标红状态**，因删除会错乱编号）。

### 3.4 穿凿点（`langgraph_agent_strategy.py::_finalize`）
- 位置：`all_search_results = self.collector.results` 之后、`citation_handler.analyze_followup` 之前（约 2218 行）。
- 伪代码：
```python
if self._verify_enabled():
    try:
        from research_verify import get_config
        from research_verify.doi_validator import DoiValidator
        from research_verify.http_client import HttpClient
        cfg = get_config()
        if cfg.module_enabled("doi_validation") and all_search_results:
            async def _run():
                async with HttpClient(cfg) as http:
                    return await DoiValidator(http, cfg).verify_many(all_search_results)
            vr = asyncio.run(_run())          # _finalize 是同步上下文
            for idx, r in vr.items():
                src = self.collector.find_by_index(idx)
                if src is not None:
                    src["_verify"] = r.model_dump()
                    src["_verify_badge"] = _badge(r)
    except Exception as exc:
        logger.warning(f"doi_validation skipped: {exc}")
```
- ⚠️ `_finalize` 在同步线程中；确认是否已有 running loop → 用 `asyncio.run`（若无）或 `run_coroutine_threadsafe`（若有）。在 T1 落地时实测确认，抽出 `_run_async(coro)` helper 兜底。
- 报告追加：在 `formatted_output = self._format_citations(...)` 之后追加 `_render_verify_section(all_search_results)`。

### 3.5 验收（1a/1b/1c）
```bash
docker exec <c> /install/.venv/bin/python -m research_verify.doi_validator \
  --doi 10.1038/s41586-020-2649-2          # 1a → verified=True
docker exec <c> ... --doi 10.9999/does-not-exist-xyz123   # 1b → verified=False
docker exec <c> ... --doi 10.1038/s41586-020-2649-2 --wrong-title  # 1c → warning
```
报告跑真实问题，肉眼确认徽标与小节。

### 3.6 单测（`tests/test_doi_validator.py`，respx mock）
- 200+title ⇒ verified True
- 404 ⇒ False
- ConnectError ⇒ None(unverified) 且不抛
- title 不符 ⇒ warnings 非空
- PMID esummary 正/负例

---

## 4. T2 —— 需求 2：条件匹配（年份/IF/语种硬约束）

### 4.1 文件与接口 `research_verify/constraint_matcher.py`
```python
class ConstraintMatcher:
    def parse(self, user_query: str, settings: dict | None = None) -> ResearchConstraint: ...
    def match(self, source: dict, c: ResearchConstraint) -> ConstraintMatch: ...
    def match_many(self, sources, c) -> dict[int, ConstraintMatch]: ...
```
- **约束来源优先级**：显式 settings（前端 UserSettings）> query 内正则 > LLM 抽取 > 无约束。
- LLM 抽取用 `self.model.invoke`（deepseek-v4-flash），输出 JSON 用 pydantic 校验；失败回落正则。

### 4.2 逻辑
- `parse`：正则抓 `20\d{2}`、`IF\s*[>≥]\s*\d+`、`英文|中文|English`；正则不足再 LLM。
- `match`：
  - `year`：`normalize_year(source)` ∈ [from,to]；越界 → `hard_violations += "year"`，`year_ok=False`。
  - `if`：`source["journal"]` → `get_db().lookup_sources_batch([journal])`：
    - **关键**：命中但 `impact_factor in (None, 0)` ⇒ `if_unknown=True`（**0.0 视为未收录**）；写 `detail["if"]=None`。
    - 命中且 `impact_factor < min_if` ⇒ `hard_violations += "if"`，`if_ok=False`。
    - 未命中 ⇒ `if_unknown=True`（不判违规、不静默通过）。
  - `lang`：从 `source["language"]` / Crossref 取；无则按引擎推断（PubMed/OpenAlex/Crossref 默认 en）；`zh` 等显式标注。
- 结果应用：`hard_violations` 非空 → 标 `source["_constraint_excluded"]=True`；**正文编号保留，Sources 小节标「不符合条件」**；若全部 excluded → 报告头显式「未找到完全满足条件的文献」，不放宽。

### 4.3 IF 查询缓存
- 每轮 `_finalize` 收集所有 journal 名 → 一次 `lookup_sources_batch`（已支持批量/去重）→ 内存 dict 传给 `match_many`，避免逐篇查库。

### 4.4 渲染
```
### 条件匹配核验（年份∈…, IF≥…, 语种=…）
| # | 期刊 | 年份 | IF | 语种 | 结论 | 说明 |
|---|------|------|----|----|------|------|
| 2 | Nature | 2026 | 17.18 | en | ✅满足 | |
| 5 | Science | 2024 | — | en | ⚠️IF未收录 | |
| 9 | Cell | 2023 | 37.23 | en | ❌年份越界 | |
```

### 4.5 穿凿点
- 与 T1 同一区域，收集阶段之后；调 `match_many` 写回。
- 前端设置：在 `research_service.py` 或 `settings` 读取 `report.year_from/min_if/language`（若已存在直接用；否则 T2 补 UserSettings 字段）。

### 4.6 验收（2a/2b/2c）
- 2a：query 带「2026年 IF≥10 英文」→ 入选文献逐篇核验，越界剔除标注。
- 2b：构造全不满足 → 报告显式「未找到完全满足条件的文献」。
- 2c：Science/Nature Medicine → `if_unknown=True` + 提示。

### 4.7 单测
- year 越界/命中；IF 0.0 → if_unknown；IF 未收录 → if_unknown；lang 不符；全不满足。

---

## 5. T3 —— 需求 3：关键词覆盖（全文/摘要命中 ≥3/4）

### 5.1 文件与接口
```python
class KeywordCoverage:
    def __init__(self, min_hits: int | None = None, ratio: float | None = None): ...
    def compute(self, source: dict, keywords: list[str]) -> KeywordCov: ...
    def extract_keywords(self, query: str, settings: dict | None = None) -> list[str]: ...
```
- 关键词来源：settings 显式 > query 提取（LLM 输出 3–6 个核心词，字符串 normalize）。

### 5.2 逻辑
- `basis`：优先 `source["full_content"] or source["body"]` → `fulltext`；否则 `snippet+abstract+title` → `abstract`；都无 → `unavailable`。
- 匹配：`normalized_text = text.casefold()`，每词 `casefold()` 后 `in` 判定（英文子串；中文直连）。
- 阈值 `threshold = max(min_hits, ceil(ratio*N))`（N=4 ⇒ ≥3）。
- `threshold_ok=False` → 标 `source["_low_keyword_coverage"]=True`，logger 记 hits/missed。
- 不物理删除；标红 + 小节展示。

### 5.3 CLI `research_verify/cli_check.py`
```bash
python -m research_verify.cli_check --dois 10.x,10.y --keywords "m6A,hepatocellular carcinoma,METTL3" --threshold 3
```
- 对 DOI/PMID 拉 PubMed efetch 全文，跑同一 `KeywordCoverage.compute` 对账。

### 5.4 渲染
```
### 关键词覆盖核验（阈值 ≥3/4）
| # | 命中 | 缺失 | 覆盖 | 依据 | 结论 |
|---|------|------|------|------|------|
| 1 | m6A,METTL3,肝细胞癌 | — | 3/4 | fulltext | ✅达标 |
| 4 | m6A | 其余3 | 1/4 | abstract | ⚠️不达标(未验证全文) |
```

### 5.5 验收（3a/3b）
- 3a：4 关键词 → 逐篇 hits/missed 与阈值判定正确。
- 3b：无全文 → `basis=abstract` + 标「基于摘要，未验证全文」。

---

## 6. T4 —— 需求 4：结论可溯源（反幻觉）

### 6.1 文件与接口 `research_verify/citation_qc.py`
```python
class CitationQc:
    def __init__(self, judge_model, cfg=None): ...
    def extract_claims(self, report_text: str) -> list[Claim]: ...        # Claim = {text, citations:list[int], line}
    def check(self, claims, collector, batch: int | None = None) -> list[ClaimCheck]: ...
    def render_section(self, checks: list[ClaimCheck]) -> str: ...        # Markdown
```
- `Claim` 轻量 dataclass（不必 pydantic）。

### 6.2 逻辑
1. `extract_claims`：按行/句切分，命中 `\[(\d+(?:\s*,\s*\d+)*)\]` 的行 → claim + citations。
2. 映射：`collector.find_by_index(n)` 取回 source；取原文片段 `full_content`/`abstract`/`snippet`（截断 1500 字）。
3. `check`：分批（`cfg.qc_batch_size≈5`）调判卷模型，temperature=0，prompt 要求返回 JSON：`{verdict, supporting_fragment, reason}`；解析失败 → `unverifiable`。
   - 原文不可得 → `unverifiable`（标「未能核对」）。
   - `unsupported` → 标红 + 附「⚠️缺少支撑」。
4. `render_section`：Markdown 表格 + JSON 落盘 `{data_dir}/logs/citation_qc_<ts>.json`。

### 6.3 判卷模型获取
- 复用 `LDR_BENCHMARK_EVALUATION_*` env 构建（`openai_endpoint` + temperature=0）。
- 实现 `_get_judge_model()`：优先用 strategy 现成 `self.model`（同端点、成本可控），若需严格 temperature=0 则另建 `ChatOpenAI`。T4 落地时二选一并实测。

### 6.4 穿凿点
- `_finalize` 末尾，`formatted_output` 生成后：`formatted_output += CitationQc.render_section(...)`；同时把 checks 写入返回值 `result["citation_qc"]=...`。

### 6.5 验收（4a–4d）
- 4a supported、4b unsupported（标红/附警）、4c unverifiable（标未能核对）、4d 全报告引用可回溯。

### 6.6 单测
- `extract_claims` 正例（多引用/多结论/无引用行）。
- mock judge 返回三态 + 解析失败降级。

---

## 7. T5 —— 联调与收尾

1. 全量单测：`pytest -q tests/`（先在容器装 `pytest pytest-asyncio respx` 或本地 venv）。
2. `docker compose up -d --build`；`docker logs` 确认 AST/import 无错、healthy。
3. 真实科研问题端到端：四需求标记同屏出现。
4. 断网演练：临时屏蔽 Crossref/PubMed，确认降级 unverified 不阻塞。
5. 灰度：逐个 `LDR_VERIFY_ENABLE_*` 关掉验证短路生效。
6. 更新 README / LLM-MODELS.md 旁注；回写行动文档勾选与完成记录。

---

## 8. 每任务执行模板（DoD，完成才勾选）

- [ ] 模块代码写入 `research_verify/<mod>.py`
- [ ] 类型注解完整、pydantic 模型齐全
- [ ] Dockerfile 校验通过（AST + import）
- [ ] 容器内 `python -m research_verify.<mod>` 自测通过
- [ ] 单测新增并通过（mock 外网）
- [ ] `_finalize` 穿凿 + 报告渲染可见
- [ ] 对应验收用例（x a/b/c）人工通过
- [ ] `LDR_VERIFY_ENABLE_<mod>=false` 短路验证
- [ ] 行动文档勾选 + 完成记录（命令/产物/截图路径）

---

## 9. 风险登记（执行期滚动更新）

| 风险 | 触发 | 应对 |
|------|------|------|
| `_finalize` 同步/异步循环冲突 | T1 起每个穿凿 | 抽 `_run_async`，检测 running loop 分支处理 |
| IF==0 误判 | T2 | 全程 `0` → `if_unknown` |
| 删除 source 破坏 [N] 编号 | T1/T2 | **保留编号仅标状态**，不物理删 |
| 判卷模型准确率 | T4 | 验收口径=「状态明确」，非「100%正确」 |
| 全文获取率低 | T3/T4 | 标 basis/未能核对，不冒充 |
| 容器内无 pytest | T5 | 用 `--target` 临时装或本地 venv |

---

*依据：`nh/local_deep_research`（热补丁+上游 venv 源码）实测：`SearchResultsCollector`(122–360)、`_finalize`(2209–2399)、`_format_citations`(base_strategy:244)、`journal_quality.db`/`lookup_sources_batch`(db.py:419)、`Source.impact_factor==0` 陷阱、Dockerfile 补丁风格、容器 env 模型/端点。*
