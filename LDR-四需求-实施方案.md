# LDR 项目四条验收需求 —— 后续详细实施方案（含技术栈）

> 目标：交付方能直观验收的**四条硬性需求**（文献真实性 / 条件匹配 / 关键词覆盖 / 结论可溯源）。
> 本方案在既有三份规划（`SCIENTIFIC_RESEARCH_OPTIMIZATION_PLAN.md`、`ldr-requirement-assessment.md`、`ldr-requirement-feasibility.md`）基础上，落到**可直接开写的文件级/代码级**粒度，并把**技术栈**逐条写明。

---

## 0. 项目背景与运行环境（重梳理）

### 0.1 架构
- **上游完整源码**：`nh/local-deep-research/`（含 `src/local_deep_research/`），被打包进镜像 `localdeepresearch/local-deep-research:ldr-ddgs`。
- **热补丁工作目录**：`nh/local_deep_research/`，`Dockerfile` 把修正文件 COPY 进镜像的 venv，已 6 处补丁（research_service、langgraph_agent_strategy、tracker、search_engine_serper、search_engine_pubmed 等）。
- **运行中实例**：`docker compose` 项目 `local_deep_research`，容器 `local_deep_research-local-deep-research-1`，端口 5000。
- **Python 运行时**：容器内 venv `Python 3.14.7`（`/install/.venv/bin/python`）。

### 0.2 当前生效模型（2026-09-24 docker inspect 实锤）
- 生成模型：**`deepseek-v4-flash`**，`http://27.30.76.162:6183/v1`，key `${LDR_BENCHMARK_EVALUATION_ENDPOINT_API_KEY}`，1M 上下文。
- 判卷模型：`deepseek-v4-flash`（同端点，temperature=0）。
- ⚠️ 旧 `LLM-MODELS.md` 记载的 S1-DeepResearch-32B(16K) 为 9-18 早期状态，**当前未用**。

### 0.3 搜索引擎现状（`ldr-monitor/ENGINE_ARCHITECTURE.md`）
- 主力可用：**PubMed(21条/查询)**、**searxng(主工具,12)**、**serper(Google,10)**。
- 配额不可用（不可依赖）：OpenAlex(429)、Brave(402)、Tavily(432)、SerpAPI(429)、Exa(402)。
- ⚠️ 需求 1 的 DOI 在线校验走 **Crossref**（`api.crossref.org`，公网、免 key、带 mailto 提额度），必要时兜底 PubMed esummary。**不依赖已失效的 OpenAlex**。

### 0.4 技术栈总览（来自 pyproject.toml / 运行环境）
| 层 | 技术 |
|----|------|
| 语言/运行时 | Python 3.14.7, asyncio/threads |
| LLM 编排 | `langchain~=1.2`、`langchain-core~=1.2`、`langchain-openai~=1.1`、`langgraph`（`langgraph_agent_strategy.py`） |
| Web 服务 | `fastapi~=0.136.3`（+ starlette 1.3.1，**勿升 0.138**） |
| HTTP 客户端 | `httpx>=0.27`、`requests>=2.33`、`aiohttp~=3.13`、`pydantic~=2.12`/`pydantic-settings~=2.12` |
| 数据/电子表格 | `pandas~=3.0`、`openpyxl~=3.1`、`xlrd~=2.0`（Excel 导出备选） |
| 检索能力 | `web_search_engines/engines/*`（pubmed 走 NCBI E-utilities：esearch/esummary/efetch；openalex 走 works API） |
| 期刊/元数据 | `journal_quality/`（SQLAlchemy，`impact_factor` 字段）、`utilities/citation_normalizer.py` |
| 日志 | `loguru`、容器日志 `/data/logs/ldr_web.log` |

### 0.5 四条需求 vs 现状（缺口聚焦）
| # | 需求 | 现状 | 缺口 |
|---|------|------|------|
| 1 | 文献真实性 | 有 DOI/PMID 抽取+去重（`langgraph_agent_strategy.py::_identity_keys`） | **无在线存在性校验**（不查 Crossref/PubMed 是否真实 resolve） |
| 2 | 条件匹配 | 引擎有时间窗、有 IF 库 | **无统一 user 硬约束逐篇核对**；IF 展示靠提示词非代码强制 |
| 3 | 关键词覆盖 | 检索是"查询→结果" | **无「关键词在全文/摘要命中数」校验** |
| 4 | 结论可溯源 | 有 `[N]`+Sources 引用、已论文级去重 | **无「结论→被引文献原文支撑」核对**，反幻觉无代码兜底 |

---

## 1. 总体设计（架构与技术决策）

### 1.1 核心思路：新增一条"科研验证链"，不动检索内核
在「检索到 → 写报告」之间插入验证，在报告产出后做后置 QC。全部走 **hot-patch 路线**：新代码集中在 `research_verify/` 包，入口穿凿只改 `langgraph_agent_strategy.py` 一两处，不重造上游检索。

```
检索引擎(PubMed/Serper/SearXNG…)  ── 现有能力，不动
   ↓  User 提供的约束(年份/IF/语种/关键词)
┌──────────────────────────────────────────────┐
│  research_verify/  (新增，Python 3.14)         │
│   A. doi_validator.py      需求1 真实性        │
│   B. constraint_matcher.py 需求2 硬约束        │
│   C. keyword_cov.py        需求3 关键词覆盖     │
│   D. citation_qc.py        需求4 结论可溯源    │
└──────────────────────────────────────────────┘
   ↓
报告生成(现有 IntegratedReportGenerator / _finalize)
   ↓
后置 QC(citation_qc) → 报告末尾追加「可溯源性/质量核查」小节 + JSON 留痕
```

### 1.2 关键技术决策
1. **校验不阻塞主流程、但必须显式留痕**：`verified=true/invalid/unverified`、`supported/partial/unsupported/unverifiable` 三等状态，禁止静默放行。检索微瑕不致整篇失败，但硬约束与真实性打标绝不静默通过（对应"不得放宽条件填充""不得凭空编造"）。
2. **配置驱动可开关**：每个模块 `enable_*` 开关 + 阈值（`min_keyword_hits`、`min_if`、`strict_year`），通过 compose env 注入，便于灰度/回滚。
3. **并发与限流**：doi/constraint/keyword 校验是外网 I/O，用 `asyncio.gather` + 信号量（复用已成文的 `aiohttp`/`httpx`），按 PubMed 10req/s、Crossref 额度做节流，避免拖慢云研究。
4. **模型上下文**：deepseek-v4-flash 1M 上下文充足，但 `citation_qc` 仍**分批/逐结论**核对，避免单次超长请求导致延迟或截断；判卷用 temperature=0 保证可复现。

---

## 2. 需求 1：文献真实性（DOI/PMID 在线校验）

### 2.1 模块文件
`local_deep_research/research_verify/doi_validator.py`

### 2.2 技术栈
- HTTP：`httpx.AsyncClient`（带超时/重试），异步并发校验。
- 数据源：**Crossref** `GET https://api.crossref.org/works/{doi}?mailto=you@x.com`（返回 200 且有 title ⇒ 真实）；**PubMed** esummary `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={pmid}`（兜底 PMID）。
- 序列化：`pydantic` v2（`BaseModel`）。
- 归一化比对：复用 `utilities.citation_normalizer.normalize_title`（或自带 `re` 归一化 title/year）。
- 日志：`loguru`。

### 2.3 类与接口（伪代码）
```python
# research_verify/doi_validator.py
from pydantic import BaseModel

class VerifyResult(BaseModel):
    doi: str | None
    pmid: str | None
    verified: bool            # True=存在且一致 / False=明确不存在 / None=unverified(网络失败)
    source: str               # "crossref" | "pubmed" | "openalex" | "unavailable"
    title_ok: bool | None
    year_ok: bool | None
    warnings: list[str]
    verified_at: str

class DoiValidator:
    def __init__(self, client: httpx.AsyncClient, timeout=10, mailto=""): ...
    async def verify(self, source: dict) -> VerifyResult: ...
    async def verify_many(self, sources: list[dict], concurrency=8) -> dict[int, VerifyResult]: ...
```

### 2.4 校验逻辑
1. 从 `source` 抽 `doi` / `pmid`（`citation_normalizer` 已有抽取）。
2. `doi` 存在 → Crossref resolve：200+title ⇒ real；404 ⇒ invalid；网络错 ⇒ unverified。
3. `pmid` 存在且无 doi → PubMed esummary 校验 result 非空。
4. **元数据一致性**：Crossref 返回 title/year vs source 的 title/year，不一致打 `warning`。
5. 无 doi 无 pmid → 用 `link` 是否 `pubmed.ncbi.../doi.org/` 可 resolve 兜底判定。

### 2.5 入口穿凿（`langgraph_agent_strategy.py::_finalize`）
收集全部 sources 后：对含 index 的每条跑 `verify_many`，把 `VerifyResult` 合并进 source dict（`source["verified"]=...`），报告中渲染「✅已核验 / ⚠️信息不一致 / ❌无效DOI / ❓未能核验」。

---

## 3. 需求 2：条件匹配（年份 / IF / 语种硬约束）

### 3.1 模块文件
`local_deep_research/research_verify/constraint_matcher.py`

### 3.2 技术栈
- 约束解析：拆分"规则抽取"（正则兜底）+ "LLM 结构化抽取"（`langchain` + `pydantic` 输出，deepseek-v4-flash 把「2026年、IF>10、英文」解析成结构体）。
- IF 数据：**SQLAlchemy** 读 `journal_quality` 库的 `Source.impact_factor`（已入库）。
- 元数据：source 的 `year`/`publication_date`/`language`/`journal` 字段 + Crossref 返回的 language/journal。
- 序列化：`pydantic`。

### 3.3 类与接口
```python
class ResearchConstraint(BaseModel):
    year_from: int | None      # e.g. 2026
    year_to: int | None
    min_if: float | None       # e.g. 10.0
    language: str | None       # e.g. "en"
    is_hard_default: bool = True

class ConstraintMatch(BaseModel):
    year_ok: bool | None
    if_ok: bool | None
    lang_ok: bool | None
    hard_violations: list[str]
    if_unknown: bool = False

class ConstraintMatcher:
    def parse(self, user_query: str, settings: dict) -> ResearchConstraint: ...   # LLM+正则
    def match(self, source: dict, c: ResearchConstraint, jq_session) -> ConstraintMatch: ...
```

### 3.4 核对逻辑
- **年份**：`source.year`（归一化到 publication year）∈ [year_from, year_to]；硬约束不满足 → `hard_violations += "year"`。
- **IF**：`source["journal"]` → `journal_quality` 查 `impact_factor` → `>= min_if`；查不到 ⇒ `if_unknown=True` 并提示"该期刊 IF 未收录"，**不静默通过**。
- **语种**：优先 Crossref/PubMed `language`；PubMed/OpenAlex/Crossref 默认判英文，中文源显式标注。
- **结果应用**：`hard_violations` 非空 ⇒ **从证据集剔除**；若全部硬约束候选都被剔除 ⇒ 报告显式返回「当前未找到完全满足这些条件的文献」，**不得放宽条件填充**（对应需求 2 的"严格满足"）。

### 3.5 入口穿凿
在 `_finalize` 的候选进入报告前跑 `ConstraintMatcher.match`，把 `ConstraintMatch` 写入 source；同时前端设置项（年份/IF/语种）持久化到 `UserSettings`（复用 `SettingsManager`）。

---

## 4. 需求 3：关键词覆盖（全文/摘要命中 ≥3/4）

### 4.1 模块文件
`local_deep_research/research_verify/keyword_cov.py`

### 4.2 技术栈
- 文本匹配：Python 原生 `str.casefold()` + `re` 子串匹配（英文统一小写、中文直接匹配）；可选增强：`thefuzz`/轻量 stemming（先不做 embedding，保证可解释与速度）。
- 全文来源：优先用已抓取的 `full_content`/`body`（fetch 产物）；回退 `abstract`+`title`，并标注 basis。
- 复核：另给 `research_verify/cli_check.py`（`argparse` CLI）对目标 DOI/PMID 拉 PubMed `efetch` 全文做离线复核。

### 4.3 类与接口
```python
class KeywordCov(BaseModel):
    total: int
    hits: list[str]          # 命中的关键词
    missed: list[str]
    coverage: float          # hits/total
    threshold_ok: bool
    basis: str               # "fulltext" | "abstract" | "unavailable"

class KeywordCoverage:
    def __init__(self, threshold_ratio=0.75, min_hits=3): ...
    def compute(self, source: dict, keywords: list[str]) -> KeywordCov: ...
```

### 4.4 逻辑
- `coverage = 命中的关键词数 / 关键词总数`；阈值默认 `max(3, ceil(0.75*N))`（4 个关键词 ⇒ ≥3）。
- 全文优先；无全文用摘要+标题并标注 basis。
- 不达标 ⇒ 标 `low_keyword_coverage`，进入剔除/降级候选。
- logger 输出每篇的 hits/missed，便于验收。

### 4.5 离线复核 CLI
```
python -m research_verify.cli_check --dois 10.xxx,10.yyy \
    --keywords m6A,"hepatocellular carcinoma",METTL3 --threshold 3
```
拉 PubMed efetch 全文跑同样的命中统计，与报告结果对账。

---

## 5. 需求 4：结论可溯源（反幻觉，提取准确性）

### 5.1 模块文件
`local_deep_research/research_verify/citation_qc.py`

### 5.2 技术栈
- 结论-引用抽取：正则 `\[(\d+)\]` 定位引用行 + 按句切分（`re.split` 句分割）；可选 LLM 结构化抽取用 `langchain`。
- 引用↔文献映射：复用 `SearchResultsCollector.find_by_index` / `_identity_map`，把 `[N]` 解回真实 source + 原文片段。
- 支撑核对：用**判卷模型**（`LDR_BENCHMARK_EVALUATION_MODEL`=deepseek-v4-flash，temperature=0）对「结论主张 vs 其引用的原文片段」做三态判定。
- 输出：报告末尾追加「可溯源性核查」小节（Markdown 表格）+ JSON 落盘。

### 5.3 类与接口
```python
class ClaimCheck(BaseModel):
    claim: str
    citations: list[int]
    sources: list[str]           # doi/url
    verdict: str                 # supported | partial | unsupported | unverifiable
    supporting_fragment: str | None
    reason: str

class CitationQc:
    def extract_claims(self, report_text: str) -> list[Claim]: ...
    def check(self, claims, collector, judge_model, batch=5) -> list[ClaimCheck]: ...
    def render_section(self, checks: list[ClaimCheck]) -> str: ...   # Markdown
```

### 5.4 逻辑
1. 抽「结论句 → `[N]` 引用编号」。
2. 找回被引文献原文片段（abstract/fetch 正文）。
3. 判卷模型逐结论核对三态：
   - `supported` = 原文片段确含支撑表述；
   - `partial` = 部分支撑；
   - `unsupported` = 原文找不到（**标红 + 从正文移除或附「⚠️缺少支撑」**，禁止保留为事实）；
   - `unverifiable` = 原文不可得，明确标注"未能核对"。
4. 汇总成 Markdown 表格追加到报告末 + 写入 JSON 留痕（验收用）。

### 5.5 防幻觉原则
- **证据不足显式标注**：凡 `evidence==null`、`unverifiable` 字段，报告统一渲染「该文献未直接提供该信息/未能核对」，禁止用模型知识补全。
- 复用已有 `evidence/evaluator.py` 的 QUOTE 抽取思路作为支撑片段来源。

---

## 6. 落地文件清单（新增 + 改动）

### 新增（都在 `nh/local_deep_research/` 热补丁目录）
| 文件 | 职责 | 需求 | 技术栈 |
|------|------|------|--------|
| `research_verify/__init__.py` | 包入口 + `VerifyConfig`(pydantic-settings) + 总开关 | — | pydantic-settings |
| `research_verify/doi_validator.py` | DOI/PMID 在线校验 | 1 | httpx.async, Crossref, PubMed eutils, pydantic |
| `research_verify/constraint_matcher.py` | 年份/IF/语种硬约束核对 | 2 | langchain+LLM 抽取, SQLAlchemy(journal_quality), pydantic |
| `research_verify/keyword_cov.py` | 关键词命中覆盖统计 | 3 | str.casefold, re |
| `research_verify/citation_qc.py` | 结论↔被引文献支撑核对 | 4 | 判卷模型(langchain), re, Markdown 渲染 |
| `research_verify/cli_check.py` | 离线复核 CLI（efetch 全文做关键词&结论对账） | 3、4 验收 | argparse, httpx, PubMed efetch |
| `research_verify/__main__.py` | `python -m research_verify` 自测入口 | 全部 | argparse |
| `tests/test_research_verify.py` | 单测（含真实 DOI/PMID 样例，pytest） | 全部 | pytest, pytest-asyncio, respx(mock HTTP) |

### 改动（穿凿为主，尽量小）
| 文件 | 改动 | 需求 |
|------|------|------|
| `langgraph_agent_strategy.py::_finalize` | 收集阶段后调 `verify_many`+`ConstraintMatcher.match`+`KeywordCoverage.compute`，合并 verified/constraint/cov 到 source | 1、2、3 |
| `langgraph_agent_strategy.py::_finalize`（响应前） | 调 `CitationQc`，把核查结果追加为报告末尾「可溯源性/质量核查」小节 | 4 |
| `Dockerfile` | COPY `research_verify/` 到 venv site-packages，加 AST 语法校验（沿用现有补丁风格） | 全部 |
| `docker-compose.yml`（可选） | 注入 `LDR_VERIFY_*` env 开关/阈值 | 全部 |

> **不做**：不新增 Crossref 检索引擎（需求 1 只是"校验存在性"，直接用 Crossref works API 即可，不进用户检索工具）；不改上游检索内核。

---

## 7. 验收用例（逐条可勾选）
准备真实 DOI/PMID 正例 + 伪造/错 DOI 负例。

| # | 验收项 | 通过标准 |
|---|--------|---------|
| 1a | 真实 DOI | Crossref 返回 `verified=true`，报告链接可打开 |
| 1b | 伪造/不存在 DOI | `invalid`，被标红/剔除，绝不当真实文献输出 |
| 1c | DOI 元数据与标题不符 | `warning`，报告给「信息不一致」提示 |
| 2a | 「2026 年 / IF≥10 / 英文」 | 入选文献逐篇通过 year/if/lang；不满足的剔除 |
| 2b | 硬约束全不满足 | 报告显式返回「未找到完全满足条件的文献」，不强行凑 |
| 2c | IF 未收录 | `if_unknown` 并提示，不静默通过 |
| 3a | 用户给 4 个关键词 | 入选文献全文/摘要命中 ≥3 才入选，命中数展示 |
| 3b | 全文缺失 | 标注「基于摘要，未验证全文」 |
| 4a | 一条结论引用 1-3 篇 | 每篇打开原文能找到支撑 ⇒ `supported` |
| 4b | 结论无支撑 | 标红/移除或标「缺少支撑」 |
| 4c | 原文不可得 | 标「未能核对」，不冒充已核对 |
| 4d | 全报告抽查 | 逐条结论的引用都能回溯到真实存在文献 |

---

## 8. 实施顺序（建议 6 步，每步可独立验收）
1. **骨架 + 配置 + HTTP 基建**：`research_verify/__init__.py`、`VerifyConfig`、`httpx.AsyncClient` 封装、Dockerfile COPY、`tests` 骨架。
2. **需求 1（DOI 校验）**：`doi_validator.py` + `_finalize` 穿凿 + 验收 1a/1b/1c。
3. **需求 2（条件匹配）**：`constraint_matcher.py`（复用 journal_quality SQLAlchemy）+ 硬约束剔除 + 验收 2a/2b/2c。
4. **需求 3（关键词覆盖）**：`keyword_cov.py` + `cli_check.py` + 验收 3a/3b。
5. **需求 4（结论可溯源）**：`citation_qc.py` + 判卷核对 + 报告末尾核查小节 + 验收 4a-4d。
6. **收尾**：全量单测 + 四条验收用例跑通 + 运行说明文档 + 灰度开关确认。

---

## 9. 风险与边界
- **外网依赖**：Crossref/PubMed 需外网；断网自动降级为 `unverified` 留痕，不阻塞主线。
- **配额**：PubMed 10req/s、Crossref 有额度，需并发限流（信号量）；**不依赖已失效的 OpenAlex**。
- **不阻塞主流程**：校验=标注/剔除/留痕，非整篇失败；但硬约束+真实性必显式标注，杜绝静默。
- **模型**：判卷用 temperature=0 + 分批核对，保证可复现、避免超长请求。
- **兼容**：在 `_identity_map` 去重后的 source 集合上跑校验，避免同一论文重复核对。
- **FastAPI 版本锁定**：保持 `fastapi~=0.136.3`，勿升，避免路由崩溃复现。

---

*依据：`nh/local-deep-research`(上游) 与 `nh/local_deep_research`(热补丁) 代码审计、`pyproject.toml` 依赖、`ldr-monitor/` 引擎实况、运行中容器 env 核实。*
