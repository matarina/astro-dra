#!/bin/bash
# LDR 持续监控采样脚本：周期性采集容器日志关键指标，追加到采样日志
# 用法: ./sample.sh  <输出文件>  [间隔秒]
CONTAINER="local_deep_research-local-deep-research-1"
OUT="${1:-/data/ningh/nh/ldr-monitor/samples.log}"
INTERVAL="${2:-120}"

LOG="/data/logs/ldr_web.log"

while true; do
  TS=$(date '+%Y-%m-%d %H:%M:%S')
  {
    echo "===== SAMPLE @ $TS ====="
    # 1) 当前活跃的 research 任务及最近进度
    echo "--active_research--"
    docker exec "$CONTAINER" sh -c "
      grep -oE 'research [a-f0-9-]{36}' $LOG 2>/dev/null | sort | uniq -c | sort -rn | head;
      echo '--recent_progress--';
      grep 'queue_progress_update' $LOG 2>/dev/null | tail -5;
      echo '--recent_milestones--';
      grep 'MILESTONE' $LOG 2>/dev/null | tail -6;
    " 2>/dev/null
    # 2) 统计类指标（自上次以来的增量由外部对比处理）
    echo "--counters--"
    docker exec "$CONTAINER" sh -c "
      echo -n 'lines_total '; wc -l < $LOG;
      echo -n 'openalex_429 '; grep -c 'OpenAlex API response status: 429' $LOG;
      echo -n 'rate_limit '; grep -c 'rate limit reached' $LOG;
      echo -n 'pdf_fail '; grep -cE 'Failed to download|Could not download' $LOG;
      echo -n 'paywall '; grep -c 'paywall' $LOG;
      echo -n 'no_results '; grep -c 'No results' $LOG;
      echo -n 'scheduler_done '; grep -c 'DOC_SCHEDULER.*Successfully' $LOG;
      echo -n 'scheduler_fail '; grep -c 'DOC_SCHEDULER.*Failed' $LOG;
      echo -n 'err '; grep -cE 'ERROR|Traceback' $LOG;
    " 2>/dev/null
    # 3) 最近 ERROR / 限流 / 失败（用于卡死与报错识别）
    echo "--recent_issues--"
    docker exec "$CONTAINER" sh -c "
      grep -E 'ERROR|Traceback|rate limit reached|FAILED|Failed to download|No results' $LOG 2>/dev/null | tail -8;
    " 2>/dev/null
    echo ""
  } >> "$OUT"
  sleep "$INTERVAL"
done
