#!/bin/bash
# ============================================================================
# LDR 搜索引擎健康探测脚本（容器内实际网络环境）
#   - 在 LDR 容器内执行探测，走容器同样的代理环境，反映真实调用结果
#   - 输出追加到 ldr-monitor/engine_probe.log（含时间戳）
#
# 用法:
#   ./search_probe.sh            # 探测一次
#   PROBE_QUERY="..." ./search_probe.sh
#   ./search_probe.sh watch 60   # 每 60s 循环探测一次（直到 Ctrl-C）
# ============================================================================
MODE="${1:-once}"
if [ "$MODE" = "watch" ]; then
  OUT="/data/ningh/nh/ldr-monitor/engine_probe.log"
  INTERVAL="${2:-60}"
else
  OUT="${1:-/data/ningh/nh/ldr-monitor/engine_probe.log}"
fi
CONTAINER="local_deep_research-local-deep-research-1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INNER="$SCRIPT_DIR/search_probe_inner.py"

run_once() {
  docker exec -i "$CONTAINER" python3 /dev/stdin < "$INNER" >> "$OUT" 2>&1
  echo >> "$OUT"
}

if [ "$MODE" = "watch" ]; then
  echo "[search_probe] watching every ${INTERVAL}s, output -> $OUT (Ctrl-C to stop)"
  while true; do run_once; sleep "$INTERVAL"; done
else
  run_once
  tail -n 13 "$OUT"
fi

