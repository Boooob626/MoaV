#!/bin/bash
# =============================================================================
# Inspect sing-box connections from logs with GeoIP country lookup
#
# Usage:
#   ./scripts/inspect-connections.sh              # All connections (last 6h)
#   ./scripts/inspect-connections.sh IR            # Filter by country
#   ./scripts/inspect-connections.sh IR 24h        # Last 24 hours
#   ./scripts/inspect-connections.sh --json        # JSON output
# =============================================================================

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

# Parse args
FILTER=""
SINCE="6h"
JSON_MODE=false
for arg in "$@"; do
    case "$arg" in
        --json) JSON_MODE=true ;;
        [0-9]*h|[0-9]*m|[0-9]*s) SINCE="$arg" ;;
        *) FILTER="$arg" ;;
    esac
done

# Base64 encode the Python script to avoid all shell escaping issues
B64SCRIPT=$(base64 < "$SCRIPT_DIR/inspect-connections.py")

docker logs moav-sing-box --since "$SINCE" 2>&1 | \
    docker exec -i \
    -e "FILTER=$FILTER" \
    -e "JSON_MODE=$JSON_MODE" \
    -e "SINCE=$SINCE" \
    -e "B64SCRIPT=$B64SCRIPT" \
    moav-singbox-exporter sh -c 'echo "$B64SCRIPT" | base64 -d | python3 /dev/stdin'
