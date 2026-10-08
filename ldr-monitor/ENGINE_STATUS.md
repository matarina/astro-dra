# LDR 搜索引擎健康基线 & 监控说明

> 生成时间：2026-09-21（容器实际网络环境下探测）
> 探测方式：在 LDR 容器内执行（走容器代理 host.docker.internal:2081），与 LDR 实际调用一致。

## 一、当前各搜索引擎状态（基线）

| 引擎 | HTTP | 耗时 | 判定 | 说明 |
|------|------|------|------|------|
| **OpenAlex** | 200 | ~1.5-2.7s | ✅ 正常 | 当前主搜索工具 `LDR_SEARCH_TOOL=openalex`；NO_PROXY 直连 |
| **PubMed** | 200 | ~1.5-1.9s | ✅ 正常 | 已配 NCBI key，额度 10req/s |
| **Serper** | 200 | ~1.3-2.7s | ✅ 正常 | Google 搜索，已配 key |
| **GitHub** | 200 | ~1.3s | ✅ 正常（API 通） | 返回 0 结果但接口可用 |
| **Brave** | 402 | ~1.3s | ❌ 配额用尽 | "Usage limit exceeded"，月度 $5 已花完（402 而非超时） |
| **Tavily** | 432 | ~1.3-1.6s | ❌ 配额超限 | "exceeds your plan's set usage limit" |
| **SerpAPI** | 429 | ~0.6-2.3s | ❌ 搜索配额耗尽 | "account has run out of searches" |
| **Exa** | 402 | ~0.7-1.3s | ❌ 余额不足 | "exceeded your credits limit" |

**结论：**
- ✅ **正常可用**：OpenAlex、PubMed、Serper、GitHub
- ⚠️ **会导致不可用（配额/余额类，非超时）**：Brave(402)、Tavily(432)、SerpAPI(429)、Exa(402)
- ⚠️ **注意**：宿主直连探测 Brave 会误判为"超时"（宿主网络直连 Brave 域名不可达，DNS 只解析出 IPv6），**必须在容器内探测**才是真实结果。

**已禁用（不参与搜索）**：Arxiv、SearXNG、Wikipedia、WikiNews、Wayback、Semantic Scholar（docker-compose 中 `*_ENABLED=false` / `*_USE_IN_AUTO_SEARCH=false`）

## 二、监控脚本

| 脚本 | 作用 |
|------|------|
| `ldr-monitor/search_probe.sh` | 容器内探测各引擎连通/耗时/限流，追加到 `engine_probe.log`。支持 `watch <秒>` 循环监控 |
| `ldr-monitor/search_probe_inner.py` | 内部实现（容器内 python 执行） |
| `ldr-monitor/sample.sh` | 原有：周期采集容器日志关键指标（活跃任务/429限流/PDF失败/ERROR）到 `samples.log` |
| `logwatch/logwatch.py` | 原有：定期日志分析+LLM解读+邮件推送 |

## 三、探测命令速查

```bash
# 单次探测
/data/ningh/nh/ldr-monitor/search_probe.sh

# 每 60s 持续监控（前台，Ctrl-C 停）—— 适合跑测试问题时并行观察
/data/ningh/nh/ldr-monitor/search_probe.sh watch 60

# 自定义查询词
PROBE_QUERY="single-cell RNA sequencing diabetic neuropathy" \
  /data/ningh/nh/ldr-monitor/search_probe.sh
```

## 四、跑真实问题时的运行时监控

跑一个 research 问题时，LDR 会在容器日志 `/data/logs/ldr_web.log` 中打印各引擎调用细节。
可用 `sample.sh`（采集 429/限流/失败等）和 `search_probe.sh watch`（实时探针）并行监控。
也可直接抓取容器日志中该 research 的搜索引擎调用记录：

```bash
docker exec local_deep_research-local-deep-research-1 sh -c \
  "grep -E 'Searching (OpenAlex|PubMed|Serper|Brave|Tavily|Exa)|rate limit|429|timeout' /data/logs/ldr_web.log | tail -50"
```
