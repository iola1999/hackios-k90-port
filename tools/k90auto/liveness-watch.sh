#!/bin/bash
# 存活轮询：一轮开始后监控 commands.jsonl 的 mtime 推进，停滞即写告警文件。
# 用法: liveness-watch.sh RUN_DIR [STALL_SECONDS] [INTERVAL_SECONDS]
#   RUN_DIR 是 round 的 run/ 目录（含 commands.jsonl）。
# 告警写到 RUN_DIR 的上一级目录：LIVENESS-ALERT（内容为一行时刻与停滞秒数）与
# liveness-watch.log（追加心跳与告警行）。本脚本不执行任何 fastboot 命令，
# 恢复动作由设备负责人按规程人工执行（先抢拉环再 oem stop）。
# 停滞判据默认 150 s：采样期 commands.jsonl 每 ~3.2 s（截图）与 ~20 s（快照）各推进一次，
# teardown 期也有 getvar/oem 命令推进；150 s 无推进即执行体失联。
set -u
RUN_DIR="${1:?usage: liveness-watch.sh RUN_DIR [STALL_SECONDS] [INTERVAL_SECONDS]}"
STALL="${2:-150}"
INTERVAL="${3:-30}"
JSONL="$RUN_DIR/commands.jsonl"
OUT_DIR="$(dirname "$RUN_DIR")"
ALERT="$OUT_DIR/LIVENESS-ALERT"
LOG="$OUT_DIR/liveness-watch.log"
echo "watch start $(date '+%H:%M:%S') pid=$$ run=$RUN_DIR stall=${STALL}s interval=${INTERVAL}s" >> "$LOG"
alerted=0
while true; do
    if [ -f "$JSONL" ]; then
        now=$(date +%s)
        mt=$(stat -f %m "$JSONL")
        age=$((now - mt))
        if [ "$age" -gt "$STALL" ]; then
            if [ "$alerted" -eq 0 ]; then
                echo "ALERT $(date '+%H:%M:%S') commands.jsonl stalled ${age}s (threshold ${STALL}s)" | tee -a "$LOG" > "$ALERT"
                alerted=1
            fi
        else
            if [ "$alerted" -eq 1 ]; then
                echo "resume $(date '+%H:%M:%S') commands.jsonl advancing again (age ${age}s)" >> "$LOG"
                rm -f "$ALERT"
                alerted=0
            fi
            echo "heartbeat $(date '+%H:%M:%S') age=${age}s" >> "$LOG"
        fi
    else
        echo "heartbeat $(date '+%H:%M:%S') commands.jsonl absent yet" >> "$LOG"
    fi
    sleep "$INTERVAL"
done
