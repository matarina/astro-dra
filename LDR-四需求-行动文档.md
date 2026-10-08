# LDR 四需求 —— 行动文档（落地执行版）

> 定位：本文件是 `LDR-四需求-实施方案.md` 的**执行落地版**，把"方案"拆解为**可直接勾选的行动步骤**。
> 用法：每完成一步，在对应 `[ ]` 前打 `[x]`，并把关键产物（文件路径/命令/截图/日志）记入"完成记录"。
> 每条需求都遵循统一闭环：**写代码 → 穿凿接入 → 容器内验证 → 验收用例 → 留痕**。

---

## 0. 当前基线（开工前先核对，勿凭记忆）

> **2026-09 基线核对结果**（已实测，非凭记忆）：

- [x] 热补丁工作目录：`nh/local_deep_research/`（Docker 构建源目录，`docker-compose.yml` + `Dockerfile` 在此）。链路 = 改此目录 → `docker compose up -d --build` → COPY 进镜像 venv。
- [x] 运行中容器：`docker ps` 可见 `local_deep_research-local-deep-research-1`，镜像 `localdeepresearch/local-deep-research:ldr-ddgs`，Status=**running / healthy**，端口 **5000**。
- [x] 模型 deepseek-v4-flash 已实锤（容器 env）：`LDR_LLM_MODEL=deepseek-v4-flash`；判卷 `LDR_BENCHMARK_EVALUATION_MODEL=deepseek-v4-flash`、`LDR_BENCHMARK_EVALUATION_TEMPERATURE=0`、`LDR_PROVIDER=openai_endpoint`；端点 `LDR_LLM_OPENAI_ENDPOINT_URL=http://27.30.76.162:6183/v1`，key `${LDR_BENCHMARK_EVALUATION_ENDPOINT_API_KEY}`。⚠️ 该 IP 在 `NO_PROXY` 中。
- [x] 搜索引擎配额：**PubMed(带 key `246f…`)、serper、searxng 可用**；OpenAlex/Brave/Tavily/SerpAPI/Exa key 虽在 env，但**配额已废，不可依赖**（与实施方案 §0.3 一致）。
  ↳ **2026-09-28 更新（见 §0.0）**：OpenAlex 实测已恢复可用（保留）；Brave/Tavily/SerpAPI/Exa/GitHub 已关闭；ollama 服务已移除。
- [x] `research_verify/` 目录：本地 `nh/local_deep_research/` 下**不存在**，需从零建包。
- [x] 容器内 Python 运行环境：**Python 3.14.7**；依赖齐全 —— httpx 0.28.1 / pydantic 2.13.4 / pydantic_settings 2.15.0 / loguru 0.7.3 / sqlalchemy 2.0.52 / langchain 1.3.15。
- [x] 外部校验 API 实测（容器内 venv python + httpx，需求1/3/4 前提）：
  - Crossref `api.crossref.org/works/{doi}` → **HTTP 200**（含 title 数据）；
  - PubMed esummary → **HTTP 200**（XML 正常）。两者容器内均可访问，外网链路通。
- [x] `langgraph_agent_strategy.py` 定位（容器内）：`/install/.venv/lib/python3.14/site-packages/local_deep_research/advanced_search_system/strategies/langgraph_agent_strategy.py`，是**热补丁覆盖**的定制版；`_finalize` 定义在 `LangGraphAgentStrategy` 类内；`SearchResultsCollector._identity_keys` 为 staticmethod，`find_by_index(idx)` 存在（1-based，返回真实 source dict）。
- [x] 需求2 数据源 `journal_quality.db`（只读 SQLite）已实测可读：`JournalQualityDB`（类名，非 `…Database`）+ `db._engine`；`models.Source` 表 `sources`，字段 `name/name_lower/issn/impact_factor/…`。
  - 数据量：**290660** 条 source，其中约 **91645** 条有非零 IF。
  - 主流期刊命中示例：Nature=17.18、Cell=37.23、The Lancet=18.42、NEJM=28.09。
  - ⚠️ **关键发现**：部分主流期刊（例：**Science=0.0、Nature Medicine=0.0**）IF 字段为 **0.0**（非 None）⇒ 若把“0.0”当有效值会误判 IF<10。**需求2 读取时须把 `impact_factor==0` 视为「未收录/未知」→ `if_unknown`**，与本文件 §2・2c 验收一致。
- [x] 镜像/版本锁定提示：镜像 tag `ldr-ddgs`（上游 `localdeepresearch/local-deep-research` + ddgs + 6 处定制补丁）；FastAPI 保持 0.136 不升。
- [x] 记录基线：已保存 `docker-compose.yml.actdoc_base_20260928` 快照；镜像 `localdeepresearch/local-deep-research:ldr-ddgs` = sha256:53eef2…d0340（2026-09-16 构建）。回滚 = 移除新增 COPY 行 + 用此快照重建即可。

**基线关键结论**：容器健康、模型/引擎现状与实施文档一致、外网校验 API 与 journal_quality 数据源均可用 ⇒ **四条需求的外部依赖全部现成可复用**，可进入 §0.1 基建。

## 0.0 项目精简记录（2026-09-28，开工前）

> 依据：本文件 §0 基线 + `ldr-monitor/` 实测。目标：关掉“不必要/已失效”功能，降低空耗与日志噪声，为四需求腾出干净基线。
> 快照：`docker-compose.yml.bak_pre_simplify_20260928_075235`；基线快照 `docker-compose.yml.actdoc_base_20260928` 保留。

### 已完成（容器内实测 + 应用内验证）

- [x] **关闭 5 个失效引擎**（2026-09-28 容器实测：Brave=402、Tavily=432、SerpAPI=429、Exa=402、GitHub=401 key 失效）：
  在 `docker-compose.yml` 注入 `LDR_SEARCH_ENGINE_WEB_{BRAVE,TAVILY,SERPAPI,EXA,GITHUB}_AGENT_ENABLED=false` + `..._USE_IN_AUTO_SEARCH=false`。
  验证：agent 工具集已不含这 5 个；自动搜索集合 = `openalex / pubmed / searxng`。
  ⚠️ **修正认知**：`ldr-monitor` 早期文档称 OpenAlex 429 失效，**2026-09-28 实测 OpenAlex 已恢复**（引擎 `run()` 返回真实结果）⇒ 保留为主力之一，未关。
- [x] **移除 ollama 服务**：删除 compose 的 `ollama` 服务、`depends_on: ollama`、`LDR_LLM_OLLAMA_URL`、`ollama_data` volume，并清理 `NO_PROXY/no_proxy` 中的 `ollama`；停删独立运行的 `ollama_service` 容器。
  （LDR 实际走外部 `openai_endpoint` deepseek-v4-flash，不经 ollama；移除后启动日志不再有 `Failed to resolve hostname ollama`。）
- [x] **GPU override 归置**：`docker-compose.gpu.override.yml` 仅为 ollama 加 GPU，随 ollama 移除改名为 `docker-compose.gpu.override.yml.orphaned_ollama_removed`（如需恢复可改回）。
- [x] **保留（未动）**：`LDR_ENABLE_FILE_LOGGING` / `LDR_USER_QUESTIONS_LOG`、`LDR_GENERAL_ENABLE_FACT_CHECKING` —— 按业务需要保留。
- [x] **清理遗留文件/日志**：删 5 个旧 compose 备份（`bak_20260908*`/`bak_20260918*`/`bak_searxng*`）、`local_deep_research/__pycache__`、`ldr-monitor/__pycache__`，以及 `ldr-monitor/` 下 `engine_calls_capture.log`/`samples.log`/`engine_probe.log`/`capture.log`/`probe_watch.out`/`watch.log`。
- [x] **重启验证**：`docker compose up -d` 重建容器 → **healthy**；`docker compose config` 有效（服务仅 `searxng` + `local-deep-research`）；启动日志无 traceback。

### 应用后当前主力引擎（基线更新）

- 可用主力：**searxng（主工具 `LDR_SEARCH_TOOL=searxng`）/ pubmed / serper / openalex**
- 已关：brave / tavily / serpapi / exa / github
- 早已禁用：arxiv / wikipedia / wikinews / wayback / semantic_scholar

### 回滚

```bash
cd nh/local_deep_research
cp docker-compose.yml.bak_pre_simplify_20260928_075235 docker-compose.yml
mv docker-compose.gpu.override.yml.orphaned_ollama_removed docker-compose.gpu.override.yml  # 如需
docker compose up -d
```


## 0.1 基建动作（先做，一次到位）

- [x] 建 `research_verify/` 包目录 + `__init__.py`（含 `VerifyConfig`(pydantic-settings) + 全局开关）。
- [x] 封装共享 HTTP 客户端（`httpx.AsyncClient`：超时≈10s、重试、信号量限流）。
- [x] 在 `tests/` 建测试骨架（pytest + pytest-asyncio + respx mock HTTP）。
- [x] 修改 `Dockerfile`：COPY `research_verify/` 到 venv site-packages + AST 语法校验（沿用现有补丁风格）。
- [x] （可选）`docker-compose.yml` 注入 `LDR_VERIFY_*` env 开关/阈值。

> **基建完成记录（2026-09-28）**
> - 新增（热补丁目录 `nh/local_deep_research/`）：`research_verify/{__init__.py,config.py,http_client.py,__main__.py}`、`tests/test_research_verify.py`。
> - `VerifyConfig`（`env_prefix=LDR_VERIFY_`）：总开关 `enable_verify` + 4 个模块开关（doi_validation/constraint_match/keyword_coverage/citation_qc）；HTTP 超时/重试/并发；Crossref mailto；需求2/3/4 阈值。`get_config()` 带 `lru_cache`。
> - `HttpClient`（异步上下文管理器）：信号量限流 + 仅对传输错误重试（指数退避）；返回 `HttpResult`，区分 `ok` / `not_found(404)` / `transport_error`（→ 降级 unverified）。
> - Dockerfile 新增 COPY → `/install/.venv/lib/python3.14/site-packages/research_verify`（顶层包），逐个 `.py` AST 校验 + 导入校验；tests/ 不进镜像。
> - compose 注入 9 项 `LDR_VERIFY_*`。
> - **验证**：`docker compose build` 成功（AST+import OK）→ 容器 healthy；`python -m research_verify` 配置正确、**Crossref ping HTTP 200**；临时装 pytest/pytest-asyncio/respx 跑骨架 **8 passed**。
> - 产物/命令：`docker exec local_deep_research-local-deep-research-1 /install/.venv/bin/python -m research_verify`。

> **关键决策（写入代码注释/README）**：校验 = **标注/剔除/留痕**，绝不静默通过、也绝不让整篇失败；断网降级为 `unverified` 留痕，不阻塞主流程。

---

## 1. 需求 1 —— 文献真实性（DOI/PMID 在线校验）

### 动作
- [x] 新建 `research_verify/doi_validator.py`：
  - [x] `VerifyResult(pydantic)`：`doi/pmid/verified/source/title_ok/year_ok/warnings/verified_at`。
  - [x] DOI 存在 → Crossref `GET https://api.crossref.org/works/{doi}?mailto=...`：200+title ⇒ real；404 ⇒ invalid；网络错 ⇒ unverified。
  - [x] 无 DOI 有 PMID → PubMed esummary（`eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={pmid}`）：result 非空 ⇒ real。
  - [x] 元数据一致性：Crossref title/year vs source title/year，不一致 → `warning`。
  - [x] 无 DOI/PMID → 用 link 是否 resolve（pubmed.ncbi/doi.org）兜底。
- [x] 穿凿 `langgraph_agent_strategy.py::_finalize`（约 2209 行）：收集全部 sources 后，对有 index 的每条跑 `verify_many`，结果合并进 source dict。
- [x] 渲染：报告中肉眼可见标「✅已核验 / ⚠️信息不一致 / ❌无效DOI / ❓未能核验」。
- 完成记录：`research_verify/{models.py,textutil.py,doi_validator.py}`；`tests/test_doi_validator.py`（7 passed）；`_finalize` 穿凿 `_attach_doi_verification`(2222) + `_render_verify_section`(2329)。容器内验收 1a/1b/1c + PMID 全过；渲染端到端过；开关短路过；镜像重建 healthy。

### 验收（对应用户目录 `LDR-四需求-实施方案.md` §7 的 1a/1b/1c）
- [x] 1a 真实 DOI → `verified=true`，报告链接可打开。
- [x] 1b 伪造/不存在 DOI → `invalid`，被标红/剔除，绝不当真实文献输出。
- [x] 1c DOI 元数据与标题不符 → `warning`，报告给「信息不一致」提示。

---

## 2. 需求 2 —— 条件匹配（年份 / IF / 语种硬约束）

### 动作
- [x] 新建 `research_verify/constraint_matcher.py`：
  - [x] `ResearchConstraint(pydantic)`：`year_from/year_to/min_if/language/is_hard_default`。
  - [x] `parse()`：LLM（deepseek-v4-flash）+ 正则把用户"2026年、IF>10、英文"解析成结构体。
  - [x] `match()`：年份 ∈ [from,to]；IF 用 SQLAlchemy 读 `journal_quality` 的 `Source.impact_factor`；语种取 Crossref/PubMed。
  - [x] 硬约束不满足 → `hard_violations`，**从证据集剔除**；全剔除 → 报告显式「未找到完全满足条件的文献」，**不放宽凑数**。
  - [x] IF 未收录 → `if_unknown=True` 提示，不静默通过。
- [x] 穿凿 `_finalize`：候选进报告前跑 `ConstraintMatcher.match`，结果写入 source。
- [x] 前端用户设置项（年份/IF/语种）持久化到 `UserSettings`（复用 `SettingsManager`）。
- 完成记录：`research_verify/constraint_matcher.py`；`tests/test_constraint_matcher.py`（13 passed）；`_finalize` 穿凿 `_attach_constraint_match` + `_render_constraint_section`。容器内 2a/2b/2c 全过（含 IF==0 陷阱、全不满足显式提示）。

### 验收（§7 的 2a/2b/2c）
- [x] 2a「2026 年 / IF≥10 / 英文」→ 入选文献逐篇通过 year/if/lang，不满足的剔除。
- [x] 2b 硬约束全不满足 → 报告显式「未找到完全满足条件的文献」，不强行凑。
- [x] 2c IF 未收录 → `if_unknown` 并提示。

---

## 3. 需求 3 —— 关键词覆盖（全文/摘要命中 ≥3/4）

### 动作
- [x] 新建 `research_verify/keyword_cov.py`：
  - [x] `KeywordCov(pydantic)`：`total/hits/missed/coverage/threshold_ok/basis`。
  - [x] 基于 `str.casefold()` + `re` 子串匹配（不做 embedding，保证可解释）。
  - [x] 全文优先（`full_content`/`body`），回退 `abstract+title`，并标 `basis`。
  - [x] 阈值默认 `max(3, ceil(0.75*N))`（4 词 ⇒ ≥3）。
  - [x] 不达标 → 标 `low_keyword_coverage`，进剔除/降级候选，logger 输出每篇 hits/missed。
- [x] 新建 `research_verify/cli_check.py`（argparse CLI，拉 PubMed efetch 全文做离线复核对账）。
- [x] 穿凿 `_finalize`：对入选文献调 `KeywordCoverage.compute`。
- 完成记录：`research_verify/{keyword_cov.py,cli_check.py}`；`tests/test_keyword_cov.py`（8 passed）；`_finalize` 穿凿 `_attach_keyword_coverage` + `_render_keyword_section`。容器内 3a/3b 全过，cli_check 真实 efetch 拉取成功。

### 验收（§7 的 3a/3b）
- [x] 3a 用户给 4 个关键词 → 入选文献全文/摘要命中 ≥3 才入选，命中数展示。
- [x] 3b 全文缺失 → 标注「基于摘要，未验证全文」。

---

## 4. 需求 4 —— 结论可溯源（反幻觉）

### 动作
- [x] 新建 `research_verify/citation_qc.py`：
  - [x] `ClaimCheck(pydantic)`：`claim/citations/sources/verdict/supporting_fragment/reason`。
  - [x] `extract_claims()`：正则 `[(\d+)]` 定位引用行 + 按句切分。
  - [x] 引用↔文献映射：复用 `SearchResultsCollector.find_by_index` / `_identity_map`（langgraph_agent_strategy.py:122、330）。
  - [x] `check()`：用**判卷模型**（temperature=0）对「结论主张 vs 被引原文片段」三态判定：`supported/partial/unsupported/unverifiable`。
  - [x] 分批（batch≈5）核对，避免超长请求/截断；`unverifiable` 明确标注，不冒充已核对。
- [x] 穿凿 `_finalize`（响应前）：把 `CitationQc.render_section()` 的 Markdown 表追加为报告末尾「可溯源性/质量核查」小节 + JSON 落盘。
- 完成记录：`research_verify/citation_qc.py`；`tests/test_citation_qc.py`（8 passed）；`_finalize` 穿凿 `_attach_citation_qc` + `apply_inline_markers` + `_write_citation_qc_json`；返回 dict 附 `citation_qc`。容器内真实判卷模型验收 4a-4d 全过，JSON 落盘 `/data/logs/citation_qc_*.json`。

### 验收（§7 的 4a–4d）
- [x] 4a 一条结论引用 1-3 篇 → 每篇打开原文能找到支撑 ⇒ `supported`。
- [x] 4b 结论无支撑 → 标红/移除或附「⚠️缺少支撑」，禁止保留为事实。
- [x] 4c 原文不可得 → 标「未能核对」，不冒充已核对。
- [x] 4d 全报告抽查 → 逐条结论的引用都能回溯到真实存在文献。

---

## 5. 联调与收尾

> **完成记录（2026-09-30）**：全链 T0-T4 完成。全量单测 **55 passed**（`tests/`，本地 venv）。镜像重建 Dockerfile 全部 AST+import+CLI 校验通过。断网降级演练（不可达端点 → `unverified` 留痕不抛）✓。总开关/逐模块开关短路演练 ✓。端到端真实判卷验收（真实 DOI+期刊+正文）四段报告串接正常，citation_qc JSON 落盘 ✓。新增 `research_verify/README.md`。

- [x] 全量单测通过：`pytest tests/`（含真实 DOI/PMID 正例 + 伪造负例）。
- [x] 重建并重启容器：`docker compose up -d --build` 后用 `docker logs` 检查 AST 校验与导入无报错。
- [x] 用一个真实科研问题完整跑一遍：四条验收一起观察报告表现。
- [x] 断网/降级演练：临时断外网，确认校验降级为 `unverified` 且主线不阻塞。
- [x] 灰度开关确认：`enable_*` 可整体/逐模块关掉，且能回滚到旧版补丁。
- [x] 更新运行说明文档（README / 复用 `LLM-MODELS.md` 旁注更新模型信息）。
- 完成记录：见上方完成记录行。

---

## 6. 风险与边界（执行时牢记）

| 风险 | 应对 |
|------|------|
| 外网依赖（Crossref/PubMed） | 断网自动降级 `unverified` 留痕，不阻塞主线 |
| 配额（PubMed 10req/s、Crossref） | asyncio.gather + 信号量限流 |
| **全文可获取率**（付费/无 OA） | 拿不到全文就标注「基于摘要/未核验」，绝不冒充 |
| 需求4 模型判断准确率 | 验收口径=「每条结论有明确核验状态」而非"模型 100% 正确" |
| 同一论文重复核对 | 在 `_identity_map` 去重后的 source 集合上跑，避免重复 |
| FastAPI 版本 | 保持 `fastapi~=0.136.3`，勿升级 |

### 明确不做
- 不新增 Crossref 检索引擎（需求1 只是"校验存在性"，用 works API 即可）。
- 不改上游检索内核。
- 不追求匿名文献 100% 覆盖全文。

---

## 7. 执行顺序建议（可独立验收）

1. **基建**（§0.1）：骨架+配置+HTTP+测试骨架+Dockerfile 接入 —— 0.5–1 人天
2. **需求1**（§1）：DOI 校验 + 穿凿 + 验收 1a/1b/1c —— 1–1.5 人天
3. **需求2**（§2）：条件匹配 + 硬约束剔除 + 验收 2a/2b/2c —— 1–1.5 人天
4. **需求3**（§3）：关键词覆盖 + CLI 复核 + 验收 3a/3b —— 1–1.5 人天
5. **需求4**（§4）：结论可溯源 + 判卷核对 + 报告尾部核查小节 + 验收 4a–4d —— 1.5–2.5 人天
6. **收尾**（§5）：联调+全量验收+文档 —— 1–1.5 人天

> **合计约 6–9.5 人天（1.5–2.5 周）**。建议**先做 1+2+3**（确定性高、验收清晰），再做 4 作防幻觉兜底。

---

## 附：本文档与既有文档的关系

- **`LDR-四需求-实施方案.md`**：技术细节、类接口、验收标准（本文的上游依据）。
- **`LDR-四需求-汇报用实施计划.md`**：面向汇报对象的简明版 + 可行性/工时评估。
- **`ldr-requirement-assessment.md` / `ldr-requirement-feasibility.md`**：早期规划（已汇总进实施方案）。
- **本文（行动文档）**：把上述落到**可勾选操作 + 完成记录**的执行清单。
