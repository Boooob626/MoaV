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

# Save logs to temp file (> file 2>&1 captures both stdout AND stderr)
LOGFILE=$(mktemp /tmp/moav-logs-XXXXXX.txt)
trap "rm -f $LOGFILE" EXIT
docker logs moav-sing-box --since "$SINCE" > "$LOGFILE" 2>&1

echo "  Fetched $(wc -l < "$LOGFILE") log lines (last $SINCE)"

# Run Python inside a container with GeoIP + the script + logs all mounted as files
docker run --rm \
    -v "$LOGFILE:/logs.txt:ro" \
    -v "$(pwd)/scripts/inspect-connections.py:/inspect.py:ro" \
    -v "$(pwd)/exporters/lib/geoip.py:/geoip_module.py:ro" \
    -v moav_moav_geoip:/geoip:ro \
    -e "FILTER=$FILTER" \
    -e "JSON_MODE=$JSON_MODE" \
    -e "SINCE=$SINCE" \
    -e "LOGFILE=/logs.txt" \
    python:3.11-alpine sh -c '
pip install --quiet --disable-pip-version-check maxminddb 2>/dev/null 1>/dev/null
exec python3 /inspect.py
'
