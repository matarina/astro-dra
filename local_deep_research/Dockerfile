# ============================================================================
# Local Deep Research — extended image
# Adds the `ddgs` package that the Wayback engine requires for DuckDuckGo
# URL discovery (the stock `localdeepresearch/local-deep-research` image
# does not ship it, which causes:
#   "Error using DuckDuckGo for URL discovery (ImportError): Could not
#    import ddgs python package.")
# ============================================================================
FROM localdeepresearch/local-deep-research:latest

# The app runs inside a Python venv at /install/.venv. Install ddgs into it
# using the system pip (the venv has no bundled pip), targeting the venv's
# site-packages so the running app can import it.
RUN /usr/local/bin/pip3 install --no-input \
        --target=/install/.venv/lib/python3.14/site-packages \
        "ddgs>=9.16"

# Verify the install is importable by the app's interpreter.
RUN /install/.venv/bin/python -c "import ddgs; print('ddgs', ddgs.__version__, 'OK')"

# ============================================================================
# CUSTOM overlay: research_service.py that additionally records each user's
# question (username + query) to <data_dir>/logs/user_questions.log as JSONL.
# Copy only this file over the image's installed copy, then re-compile/verify.
# ============================================================================
COPY research_service.py /install/.venv/lib/python3.14/site-packages/local_deep_research/web/services/research_service.py
RUN /install/.venv/bin/python -c "import ast; ast.parse(open('/install/.venv/lib/python3.14/site-packages/local_deep_research/web/services/research_service.py', encoding='utf-8').read()); print('research_service.py syntax OK')"

# Deduplicate agent search results before citation numbers are assigned, so
# repeated URLs and the same paper returned by multiple engines are synthesized once.
COPY langgraph_agent_strategy.py /install/.venv/lib/python3.14/site-packages/local_deep_research/advanced_search_system/strategies/langgraph_agent_strategy.py
RUN /install/.venv/bin/python -c "import ast; ast.parse(open('/install/.venv/lib/python3.14/site-packages/local_deep_research/advanced_search_system/strategies/langgraph_agent_strategy.py', encoding='utf-8').read()); print('langgraph_agent_strategy.py syntax OK')"

# arXiv rate-limit mitigation: floor arXiv's adaptive wait time at 3s.
# The estimator starts optimistic at 0.1s and only learns upward after
# failures, which hammers export.arxiv.org and caused ~183 HTTP 429s.
COPY overlay/tracker.py /install/.venv/lib/python3.14/site-packages/local_deep_research/web_search_engines/rate_limiting/tracker.py
RUN /install/.venv/bin/python -c "import ast; ast.parse(open('/install/.venv/lib/python3.14/site-packages/local_deep_research/web_search_engines/rate_limiting/tracker.py', encoding='utf-8').read()); print('tracker.py syntax OK')"

# Serper(Google) query-quote fix: strip stray double quotes from LLM-generated
# web queries before building the Serper payload. Serper/Google rejects queries
# containing double quotes with HTTP 400 ("Bad Request"), which converted every
# valid search into "No results" (~30 events per research session).
COPY search_engine_serper.py /install/.venv/lib/python3.14/site-packages/local_deep_research/web_search_engines/engines/search_engine_serper.py
RUN /install/.venv/bin/python -c "import ast; ast.parse(open('/install/.venv/lib/python3.14/site-packages/local_deep_research/web_search_engines/engines/search_engine_serper.py', encoding='utf-8').read()); print('search_engine_serper.py syntax OK')"

# PubMed query-quote fix (mirrors the Serper fix): LLM-generated/optimized
# queries sometimes carry a stray closing quote right before a field tag
# (e.g. bacteria"[Title/Abstract]), which PubMed's esearch parser rejects and
# turns into "found 0 results". Strip double quotes from the query in both
# _get_result_count and _search_pubmed before it reaches E-utilities.
COPY search_engine_pubmed.py /install/.venv/lib/python3.14/site-packages/local_deep_research/web_search_engines/engines/search_engine_pubmed.py
RUN /install/.venv/bin/python -c "import ast; ast.parse(open('/install/.venv/lib/python3.14/site-packages/local_deep_research/web_search_engines/engines/search_engine_pubmed.py', encoding='utf-8').read()); print('search_engine_pubmed.py syntax OK')"

# ============================================================================
# research_verify/ — 新增的“科研验证链”包（四需求的地基，§0.1）。
# 顶层包名 research_verify，装入 venv site-packages 根目录，
# 供 langgraph_agent_strategy._finalize 穿凿时 `from research_verify import ...`。
# 仅 COPY 包本体（tests/ 不进生产镜像）。安装后逐个 .py 做 AST 语法校验。
# ============================================================================
COPY research_verify /install/.venv/lib/python3.14/site-packages/research_verify
RUN /install/.venv/bin/python -c "import ast, pathlib; root = pathlib.Path('/install/.venv/lib/python3.14/site-packages/research_verify'); files = sorted(root.rglob('*.py')); [ast.parse(f.read_text(encoding='utf-8'), filename=str(f)) for f in files]; print('research_verify syntax OK:', [f.name for f in files])"
# 确认包可被应用解释器导入（不触发外网）。
RUN /install/.venv/bin/python -c "import research_verify; from research_verify import VerifyConfig, HttpClient, HttpResult, VerifyResult, ResearchConstraint, ConstraintMatch, KeywordCov, ClaimCheck; print('research_verify import OK', research_verify.__version__)"
RUN /install/.venv/bin/python -c "from research_verify.doi_validator import DoiValidator, badge_for; from research_verify.constraint_matcher import ConstraintMatcher; from research_verify.keyword_cov import KeywordCoverage; from research_verify.citation_qc import CitationQc; from research_verify.textutil import normalize_title; print('research_verify T0-T4 modules import OK')"
RUN /install/.venv/bin/python -m research_verify.citation_qc --text 'x [1].' >/dev/null && echo 'research_verify citation_qc CLI OK'

# No custom CMD/ENTRYPOINT override — inherit upstream defaults
# (entrypoint=/usr/local/bin/ldr_entrypoint.sh, cmd=ldr-web)
