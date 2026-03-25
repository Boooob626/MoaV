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

# Run Python script inside singbox-exporter (has GeoIP + network access)
# Mount the script via docker run with --volumes-from to access GeoIP data
# Use a temporary container that shares the geoip volume
docker logs moav-sing-box --since "$SINCE" 2>&1 | \
    docker run --rm -i \
    --network moav_moav_net \
    -v moav_moav_geoip:/geoip:ro \
    -v "$(pwd)/scripts/inspect-connections.py:/inspect.py:ro" \
    -v "$(pwd)/exporters/singbox:/app:ro" \
    -e "FILTER=$FILTER" \
    -e "JSON_MODE=$JSON_MODE" \
    -e "SINCE=$SINCE" \
    python:3.11-alpine python3 /inspect.py
