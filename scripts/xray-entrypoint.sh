#!/bin/bash
# Xray-core entrypoint script (VLESS+XHTTP+Stealth behind Caddy TLS frontend)
set -e

CONFIG_FILE="/etc/xray/config.json"

echo "[Xray] Starting Xray-core (VLESS+XHTTP+Stealth)..."
echo "[Xray] Running behind Caddy TLS frontend on internal port 8443"

# Check for config
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "[Xray] ERROR: config.json not found at $CONFIG_FILE"
    exit 1
fi

echo "[Xray] Configuration:"
echo "  - Config: $CONFIG_FILE"
echo "  - Version: $(xray version | head -1)"

# Check for Stats API configuration
if grep -q '"api-in"' "$CONFIG_FILE"; then
    echo "  - Stats API: enabled (port 10085)"
else
    echo "  - Stats API: NOT configured (per-user traffic metrics will be unavailable)"
fi

# Start Xray
exec xray run -c "$CONFIG_FILE"
