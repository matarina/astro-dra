# LDR 搜索引擎全景与现状梳理

> 历史说明：本页为2026年9月的模型/搜索基线，默认模型、来源、代理及操作路径不代表当前实例。最新见[当前状态](../docs/current-status.md)及[文档目录](../docs/document-catalog.md)。

> 基于 2026-09-21 重建后容器内实测（SettingsManager snapshot → create_search_engine → run() 逐引擎验证）
> 关键区分：**「搜索引擎」在 LDR 里是一个统称**，包含了学术库、医学库、通用网页搜索 API、自托管聚合器、书籍库、化学库等，本质都是"给 LLM 提供结果的检索源"。

---

## 一、核心概念：主工具 vs 专业工具

LDR 里所有"引擎"本质一样——都是 LLM 可调用的检索工具，但分两类角色：

| 角色 | 是什么 | 当前值 |
|------|--------|--------|
| **主搜索工具 search.tool** | LLM 的默认/首选 `web_search`，用于通用探索 | **openalex**（⚠️ 已失效） |
| **专业引擎 search_[engine]** | LLM 按领域选用的专门工具（search_pubmed/search_searxng…） | PubMed、searxng、serper 等 |

> **PubMed 属于搜索引擎吗？** 是。在 LDR 里 PubMed 就是一个搜索引擎实现（`search_engine_pubmed`），注册成 `search_pubmed` 工具，只是它检索的是医学文献库（NCBI E-utilities），而非通用网页。学术库、书籍库、化学库同理。

---

## 二、当前已注册的引擎全景（agent 工具）

以下 14 个引擎注册为 LLM 可用工具（`agent_enabled=True`）：

### 学术 / 医学文献（科研主力）
| 引擎 | 检索什么 | key | 实际状态 |
|------|---------|-----|---------|
| **openalex** | 2.5亿+学术论文（全学科） | 无 | ❌ **429 额度用尽**（主工具已失效） |
| **pubmed** | PubMed 医学文献（NCBI） | ✓ | ✅ **21 条/查询，正常** |
| **zenodo** | 研究数据集/软件/文献(DOI) | 无 | ✅ 可用（需实测数量） |
| **stackexchange** | StackOverflow 等编程问答 | 无 | ✅ 可用 |

### 通用网页搜索
| 引擎 | 检索什么 | key | 实际状态 |
|------|---------|-----|---------|
| **searxng** | 自托管元搜索(聚合 bing/startpage/mojeek…) | 无 | ✅ **10 条/查询，刚接入可用** |
| **serper** | Google 搜索 API | ✓ | ✅ **10 条/查询，正常** |
| **brave** | Brave 搜索引擎 | ✓ | ❌ 402 配额用尽 |
| **tavily** | AI 研究搜索(带答案抽取) | ✓ | ❌ 401/432 key 无效或超限 |
| **serpapi** | Google 搜索 API | ✓ | ❌ 401 / 429 配额耗尽 |
| **exa** | 神经语义搜索(AI优化) | ✓ | ❌ 402 余额不足 |

### 书籍 / 化学 / 本地
| 引擎 | 检索什么 | key | 状态 |
|------|---------|-----|------|
| **gutenberg** | 7万+公版书全文(Gutendex) | 无 | ✅ 可用 |
| **openlibrary** | 200万+书籍元数据(Internet Archive) | 无 | ✅ 可用 |
| **pubchem** | 化学化合物/结构/活性 | 无 | ✅ 可用 |
| **library** | 本地 RAG/文档库 | 无 | 需本地检索器 |

---

## 三、主次 / 自动搜索逻辑

### 自动搜索集合（use_in_auto_search=True）—— 前端发起的"自动研究"会自动调用的引擎
```
github · pubmed · searxng · openalex
```
> 但 openalex 已失效，实际自动搜索有效的是 **pubmed + searxng**（github 配了接口但经常 0 结果）。

### 为什么 openalex 是主工具、其他是专业工具
- **主工具** = 一个，由 `search.tool` 决定，LLM 默认调 `web_search` 用它做初始探索，覆盖全学科。
- **专业工具** = 多个，`_build_tools` 把每个 eligible 引擎注册为 `search_*`，LLM 根据题目领域挑选（医学→pubmed、通用→searxng、编程→stackexchange…）。
- **自动搜索** = 前端按钮，并行调 use_in_auto_search 的引擎，不经过 LLM 选工具。

### 引擎分级（eligibility 过滤链，`list_eligible_engine_configs`）
```
agent_enabled → use_in_auto_search → 出口策略(egress) → is_available(探活)
```
不可用的引擎**不注册成工具**，LLM 就看不到（避免拿坏工具）。所以 brave/tavily/serpapi/exa 虽配置了 key，但实际 402/401 导致它们即使注册了也用不了。

---

## 四、⚠️ 本次重要发现：主工具 OpenAlex 已失效

- 连续多次探测 `api.openalex.org` 均返回 **429 "Insufficient budget. This request has no API key"**
- LDR 引擎 `run('hepatocellular carcinoma m6A')` → **返回 0 结果**（429 被静默吞掉成空）
- **影响**：`search.tool=openalex` 现在 `web_search` 主工具实际搜不到东西，自动研究和 LLM 初始探索会拿到空结果

### 可选对策
1. **切换主工具到 searxng 或 pubmed**：`LDR_SEARCH_TOOL=searxng`（通用）或 `pubmed`（生物医学），需改 compose + 重建
2. 给 openalex 配一个真实 API key（`LDR_SEARCH_ENGINE_WEB_OPENALEX_API_KEY`），绕过无 key 免费额度限制
3. 等待 OpenAlex 免费额度窗口重置（通常按时间窗口）

---

## 五、一句话总结

LDR 的"搜索引擎"是**一个包含大量异构检索源的统称**：学术库(openalex/zenodo)、医学库(pubmed)、通用网页(searxng/serper/brave/tavily/serpapi/exa)、书籍(gutenberg/openlibrary)、化学(pubchem)、代码问答(stackexchange)、本地(library)。
- **主工具** = search.tool 一个（现 openalex，已失效需处理）
- **专业工具** = 其余可用的，LLM 按需选
- **可用主力** = **pubmed + searxng + serper**（实测稳定出结果）
- **配额不可用** = brave(402) / tavily(401) / serpapi(401) / exa(402) / **openalex(429 新失效)**

---

## 六、主工具切换为 searxng（2026-09-21）

因 OpenAlex 免费额度耗尽（429），将主搜索工具从 openalex 切换到 searxng：

**改动**：`LDR_SEARCH_TOOL=openalex → searxng`（docker-compose.yml），重建容器生效。

**验证结果**：
- `search.tool = searxng` ✅
- `create_search_engine('searxng')` 作为主工具 run() → **12 条结果**（含 "The regulatory role of m6A in cancer metastasis" 等学术结果）✅
- agent 工具集合含 searxng；自动搜索 = github, openalex, pubmed, searxng ✅
- 日志无 searxng 错误 ✅

**当前可用主力**：pubmed(21) / searxng(主,12) / serper(10)
**配额不可用**：brave(402) / tavily(401) / serpapi(401) / exa(402) / openalex(429)
