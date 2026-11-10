#!/usr/bin/env python3
"""
LDR 搜索引擎健康探测（容器内运行版）
在 LDR 容器内执行，走容器同样的代理/网络环境，反映 LDR 实际调用的真实结果。
用法:
    docker exec -i local_deep_research-local-deep-research-1 \
        python3 /dev/stdin  < search_probe_inner.py
输出: 每引擎一行: 名称 HTTP 耗时 判定 说明
"""
import os, sys, json, time, urllib.request, urllib.error

Q = os.environ.get("PROBE_QUERY", "metabolic intermediates lactate succinate pain signaling nociceptor")

KEYS = {
    "OPENALEX_EMAIL": "${LDR_VERIFY_CROSSREF_MAILTO}",
    "BRAVE":   "${LDR_SEARCH_ENGINE_WEB_BRAVE_API_KEY}",
    "TAVILY":  "${LDR_SEARCH_ENGINE_WEB_TAVILY_API_KEY}",
    "SERPAPI": "${LDR_SEARCH_ENGINE_WEB_SERPAPI_API_KEY}",
    "SERPER":  "${LDR_SEARCH_ENGINE_WEB_SERPER_API_KEY}",
    "GITHUB":  "${LDR_SEARCH_ENGINE_WEB_GITHUB_API_KEY}",
    "EXA":     "${LDR_SEARCH_ENGINE_WEB_EXA_API_KEY}",
    "PUBMED":  "${LDR_SEARCH_ENGINE_WEB_PUBMED_API_KEY}",
}
TIMEOUT = 30

def _do(url, headers=None, data=None):
    req = urllib.request.Request(url, headers=headers or {})
    if data is not None:
        req.data = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    return urllib.request.urlopen(req, timeout=TIMEOUT)

def probe(name, url, headers=None, data=None):
    t0 = time.time()
    try:
        r = _do(url, headers, data)
        body = r.read()[:120]
        el = time.time() - t0
        code = r.status
        verdict = "OK"
        return (name, code, el, verdict, body)
    except urllib.error.HTTPError as e:
        el = time.time() - t0
        body = e.read()[:160]
        code = e.code
        d = body.decode(errors="ignore").lower()
        if code == 429: verdict = "RATE_LIMIT-429"
        elif code == 402: verdict = "PAYMENT/QUOTA-402"
        elif code == 432: verdict = "QUOTA-432"
        elif code in (401,): verdict = "UNAUTH-401"
        elif code == 403: verdict = "FORBIDDEN-403"
        else: verdict = f"HTTP:{code}"
        return (name, code, el, verdict, body)
    except Exception as e:
        el = time.time() - t0
        return (name, "-", el, f"ERR:{type(e).__name__}", str(e)[:100].encode())

q = Q.replace(" ", "+")
results = []
results.append(probe("OpenAlex",
    f"https://api.openalex.org/works?search={q}&per-page=3",
    {"User-Agent": f"mailto:{KEYS['OPENALEX_EMAIL']}"}))
results.append(probe("PubMed",
    f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={q}&retmax=3&api_key={KEYS['PUBMED']}"))
results.append(probe("Serper",
    "https://google.serper.dev/search",
    {"X-API-KEY": KEYS["SERPER"]},
    {"q": Q, "num": 3}))
results.append(probe("GitHub",
    f"https://api.github.com/search/repositories?q={q}&per_page=3",
    {"Authorization": f"Bearer {KEYS['GITHUB']}", "Accept": "application/vnd.github+json"}))
results.append(probe("Brave",
    f"https://api.search.brave.com/res/v1/web/search?q={q}&count=3",
    {"X-Subscription-Token": KEYS["BRAVE"], "Accept": "application/json"}))
results.append(probe("Tavily",
    "https://api.tavily.com/search",
    data={"api_key": KEYS["TAVILY"], "query": Q, "max_results": 3}))
results.append(probe("SerpAPI",
    f"https://serpapi.com/search.json?engine=google&q={q}&num=3&api_key={KEYS['SERPAPI']}"))
results.append(probe("Exa",
    "https://api.exa.ai/search",
    {"x-api-key": KEYS["EXA"]},
    {"query": Q, "numResults": 3}))

print(f"PROBE @ {time.strftime('%Y-%m-%d %H:%M:%S')} | query='{Q}'")
print(f"PROXY={os.environ.get('HTTPS_PROXY','(direct)')}")
print("-" * 78)
for name, code, el, verdict, body in results:
    note = " " + body.decode(errors="ignore").replace("\n", " ")[:70]
    print(f"{name:<10} HTTP={code:<4} {el:6.2f}s  ->  {verdict:<18}{note}")
