#!/bin/bash
# 持续抓取容器日志中搜索引擎调用/错误，追加到 engine_calls_capture.log
CONTAINER="local_deep_research-local-deep-research-1"
OUT="/data/ningh/nh/ldr-monitor/engine_calls_capture.log"
LAST=""
while true; do
  TS=$(date '+%Y-%m-%d %H:%M:%S')
  MARKER="===== CAPTURE @ $TS ====="
  { echo "$MARKER"
    docker exec "$CONTAINER" sh -c "grep -E 'Using search tool|Investigating subtopic|api.openalex|google.serper|tavily.com|api.search.brave|serpapi.com|api.exa.ai|api.github.com|eutils|api.tavily|rate limit|429|432|402|timed out|Timeout|Traceback' /data/logs/ldr_web.log 2>/dev/null | grep -E '11:0[5-9]|11:1[0-9]' | tail -30" 2>/dev/null
  } >> "$OUT"
  sleep 60
done
