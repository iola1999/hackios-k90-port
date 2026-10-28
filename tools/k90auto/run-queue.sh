#!/bin/bash
# Run unattended payload directories one after another: run-auto.py, then loader recovery when the
# USB reset fell back to Android B. Stops at the first run that does not end in loader idle.
# usage: tools/k90auto/run-queue.sh RUN_DIR...   (RUN_DIR as make-payload.py printed it)
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
for dir in "$@"; do
	name=$(basename "$dir")
	parent=$(dirname "$dir")
	# A payload directory outlives its build: make-payload.py refuses to reuse a directory, but this
	# loop then ran whatever the previous build had left there. Read the manifest back and check the
	# payload it names, so a build that failed cannot start a round with the previous payload.
	payload=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["payload"]["path"])' "$dir/manifest.json" 2>/dev/null || true)
	if [ -z "$payload" ]; then
		echo "QUEUE stop: $dir/manifest.json names no payload; the build before this run did not finish"
		exit 1
	fi
	if [ ! -f "$payload" ]; then
		echo "QUEUE stop: $dir/manifest.json names $payload, which is not on disk"
		exit 1
	fi
	echo "QUEUE start $name $(date +%H:%M:%S) payload $(shasum -a 256 "$payload" | cut -c1-16)"
	status=0
	python3 "$HERE/run-auto.py" "$dir" "${RUN_SECONDS:-420}" "${RUN_TIMING:-3,100,20}" > "$parent/run-$name.log" 2>&1 || status=$?
	tail -1 "$parent/run-$name.log"
	if grep -q '"mode": "android"' "$dir/run/reboot.json" 2>/dev/null; then
		python3 "$HERE/recover-loader.py" "$parent/loader-recover-$name" 2>&1 | tail -1
	fi
	if ! fastboot -s xnuloader getvar result 2>&1 | grep -q "result: idle"; then
		echo "QUEUE stop: loader not idle after $name"
		exit 1
	fi
	if [ "$status" -ne 0 ]; then
		echo "QUEUE stop: run failed for $name; see $parent/run-$name.log"
		exit "$status"
	fi
	echo "QUEUE done $name $(date +%H:%M:%S)"
done
