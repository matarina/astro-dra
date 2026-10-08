# LDR 需求可行性评估（代码审计版）

> 评估对象：`nh/local_deep_research`（团队热补丁工作目录）+ `nh/local-deep-research`（上游完整源码，含 `src/local_deep_research/`）
> 依据：对实际代码、`SCIENTIFIC_RESEARCH_OPTIMIZATION_PLAN.md`、`LLM-MODELS.md`、`user_questions.log` 的逐项核对。
> 结论分级：✅ 已实现 / ⚠️ 部分实现（有缺口）/ ❌ 未实现 / 🟡 需业务确认

## 架构速览（帮助理解判断依据）

| 部分 | 位置 | 作用 |
|---|---|---|
| 上游完整源码 | `nh/local-deep-research/`（src/local_deep_research/） | 打包成镜像 `ldr-ddgs`，运行 Web 应用主体（Web UI、检索引擎、策略、报告生成器、导出器、期刊分级 DB、文档加载器） |
| 团队热补丁 | `nh/local_deep_research/*.py` | research_service（用户问题日志）、langgraph_agent_strategy（引用去重）、search_engine_pubmed/serper（引号修复）、overlay/tracker（arXiv 限速）；经 Dockerfile COPY 覆盖进镜像 |
| 当前模型 | OpenAI 兼容端点 S1-DeepResearch-32B（16K 上下文），见 LLM-MODELS.md | 生成 + 判卷 |
| 搜索引擎 | 默认 OpenAlex；另配 PubMed、arXiv、Serper(Google)、Brave、Tavily、Semantic Scholar、OpenAlex、Crossref(计划)、SearXNG(本地) | |

---

## 逐条评估

| 需求点 | 说明 | 能否实现 | 判断依据（代码/文件） |
|---|---|---|---|
| 输入类型 | 自然语言、文档、图片、表格 | ✅ 自然语言+文档+Excel 表格已支持；图片仅 OCR 文本，无多模态问答 | `document_loaders/__init__.py`（PDF/Word/Excel/CSV/图片OCR 等 35+ 格式）、`bytes_loader.py` |
| 输入自动解析 | 自动解析关键词、研究方向 | ✅ 已实现（LLM 问题分解 + 子题并行研究） | `langgraph_agent_strategy.py`（research_subtopic 工具）、`focused_iteration_strategy.py`、`decomposition_question.py` |
| 检索相关性强 | 结果必须高度贴合课题 | ⚠️ 有相关性过滤（cross_engine_filter），但无"科研硬约束层"强制把控 | `cross_engine_filter.py`、`source_based_strategy.py`；方案 §3.1/§3.6 hard_constraint_filter（未落地） |
| 文献真实性 | 文献必须真实存在、可溯源 | ⚠️ 有 DOI/PMID 抽取 + Paper 表唯一约束；**无在线 DOI/PMID 权威校验、无真实性 validator** | `citation_normalizer`、Paper 表 unique；方案 §3.2 metadata_validator（未落地） |
| 可检索/下载 | 能下载原文，下载不了有替代方案 | ✅ OA 原文可下载；付费/无 OA 可回退摘要+PMC 全文 | `research_library/downloaders/`：openalex/arxiv/biorxiv/direct_pdf/pubmed/semantic_scholar/html/playwright_html |
| 期刊影响因子 | 报告展示 IF；硬需求需代码强制格式化输出 | ⚠️ IF 数据已入库可查；**是否进报告主要靠提示词，未做代码级强制格式化** | `journal_quality/db.py`、`journal_quality/models.py`（impact_factor 字段）、`web/routers/metrics.py` |
| 上下文记忆 | 记住用户检索历史与偏好 | ✅ 多轮 follow-up + 上下文管理（会话级）；⚠️ 非"跨会话用户偏好库" | `strategies/followup/enhanced_contextual_followup.py`、`knowledge/followup_context_manager.py`、`web/routers/followup.py` |
| 追问澄清 | 客户提问模糊时主动追问 | ❌ 未实现——系统 prompt **刻意禁止**追问 | `langgraph_agent_strategy.py` L1607/L2632："Do NOT ask clarifying questions—provide findings directly" |
| 文献时间限定 | 年限可限定（2021-2026） | ⚠️ 引擎层有时间窗（reldate/自适应），但非用户级硬约束，多靠 prompt/自动推导 | `search_engine_pubmed.py`（time window、`_expand_time_window`） |
| 引用可溯源 | 结果给出引用出处、DOI、URL | ✅ 正文 `[N]` 引用 + Sources 汇总；热补丁已做引用去重 | `langgraph_agent_strategy._finalize`、`_format_citations`、`citation_handler` |
| 文献可排序 | 按相关度、IF、发表时间筛选排序 | ⚠️ 相关度排序有；**按 IF/时间显式排序接口无**，靠 final_max_results + journal_reputation 过滤 | `cross_engine_filter.py`、`journal_reputation_filter.py` |
| 中英文支持 | 中英文文献均需覆盖 | ⚠️ 有 search.search_language 设置项；底层英文引擎为主，**中文文献/中文规范化引用无专设** | `web/routers/settings.py`（search.search_language） |
| 参考文献格式规范 | 期刊、作者、题目、时间 | ✅ 部分：RIS/LaTeX 等导出已实现；统一/中文化格式化仍靠提示词 | `exporters/`（ris/latex/odt/pdf/quarto） |
| 保密 | 不能上传外网；个人+管理权限分级 | ⚠️ 有登录鉴权、按 username 隔离数据；**无角色/权限分级体系**；核心检索（PubMed/OpenAlex 等）必须走外网 | `web/app.py`、`fastapi_app.py`、`auth.py`、`followup.py`（用户归属校验） |
| 响应时间与速度 | 输入到文献报告 1 天之内 | 🟡 流式输出由前端逐步呈现（实际远快于 1 天）；但完整 deep research 数分钟~数小时，**无 SLA / SearchBudget 保证** | `start_research_process`、`cleanup_research_resources`；方案 §3.8（未落地） |
| 场景定位 | 单细胞、空间组学适用 | ✅ 引擎层已含 scRNA/spatial 处理，且实际用户大量使用 | `search_engine_pubmed.py`（"single-cell RNA sequencing" phrase）；`user_questions.log` |
| 多轮对话与导出 | 对话精华一键导出为 Excel 实验记录表 | ❌ **无 Excel 导出**（现有 PDF/ODT/LaTeX/Quarto/RIS/Markdown）；Excel 仅作为**输入**支持 | `exporters/registry.py`（无 xlsx）；`document_loaders`（xls/xlsx 可导入） |
| 文献智能体报告格式 | 目录/摘要/关键词段落/小结/总结/来源/综述/实验性文章 | ⚠️ 现有 `IntegratedReportGenerator` 是主题/综述式；**无 paper-centric 逐篇模板、无"综述/实验性文章"分类模板** | `report_generator.py`；`TopicOrganizationStrategy` 未接入报告器；方案 §3.7（未落地） |
| 方案智能体报告格式 | 摘要/科学问题与假说/文献证据/实验方法提取 | ❌ **无独立"方案智能体"**。仅文献调研智能体；科学问题/假说/实验方法提取无工作流 | 全库检索无 proposal/方案 agent |
| 智能体软件 | 可操作 UI，公司网络之外可用 | 🟡 已是 Web UI 且可对暴露（5000 端口+登录）；对外可用度是部署/合规决策 | `docker-compose.yml`（5000）、`auth.py` |
| 文献知识库沉淀 | 检索文献/提炼结果/方案存档，后续复用积累 | ✅ 用户隔离的历史 + follow-up 复用 + Library/RAG 集合已实现；⚠️ 跨会话结构化"方案知识库"为计划项 | `web/routers/history.py`、`library*.py`、`rag.py`；方案 §3.10 ReferenceManager（未落地） |

---

## 结论汇总

### ✅ 直接可用（无需动作）
- 输入类型（自然语言/文档/表格/图片OCR）
- 输入自动解析（关键词/研究方向分解）
- 可检索/下载（OA 原文 + 摘要/PMC 回退）
- 引用可溯源（`[N]`+DOI/URL/Sources，已去重）
- 多轮 follow-up 上下文复用（会话级）

### ⚠️ 有缺口，加固后才能满足硬需求
- 文献真实性：需补在线 DOI/PMID 校验（§3.2）
- 期刊影响因子强制展示：需在报告/引用阶段代码强制格式化输出，而非只靠提示词
- 时间限定 / 硬约束：需补科研约束解析 + hard_constraint_filter（§3.1/§3.6）
- 检索相关性：需硬约束相关性双阈值
- 保密权限分级：现有登录/用户隔离，缺个人 vs 管理员角色体系

### ❌ 明确未实现（需新开发）
- 追问澄清（当前 prompt 明确禁止，需专项开发主动澄清路由）
- Excel 导出实验记录表（需新增 xlsx exporter）
- 方案智能体（科学问题/假说/实验方法提取）
- 文献报告 paper-centric / 综述·实验性文章分类模板

### 🟡 需业务确认（SLA / 部署类）
- 响应时间 1 天内：流式实际快很多，但要承诺 SLA 需引入限时/SearchBudget
- "公司网络之外可用"：Web 可对外，但暴露范围/合规是部署决策

---

## 建议的落地优先级（供排期）
1. Excel 导出 + 方案智能体 + 追问澄清（纯新增，需求明确）
2. 文献真实性 DOI 校验 + IF 强制输出 + 硬约束过滤（可信度，P0）
3. 报告模板（paper-centric / 综述分类）+ 排序接口（报告/交付，P1）
4. 角色权限分级 + SLA/预算（治理与效率，P2）
