#!/bin/sh

# =============================================================================
# sing-box entrypoint with logging
# =============================================================================

CONFIG_FILE="${CONFIG_FILE:-/etc/sing-box/config.json}"

echo "[sing-box] Starting sing-box multi-protocol proxy"
echo "[sing-box] Config: $CONFIG_FILE"

# Check config exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "[sing-box] ERROR: Config file not found at $CONFIG_FILE"
    echo "[sing-box] Run bootstrap first to generate configuration"
    exit 1
fi

# Copy config to writable location (source may be read-only mount)
RUNTIME_CONFIG="/tmp/sing-box-config.json"
cp "$CONFIG_FILE" "$RUNTIME_CONFIG"

# Validate config
echo "[sing-box] Validating configuration..."
if ! sing-box check -c "$RUNTIME_CONFIG"; then
    echo "[sing-box] ERROR: Configuration validation failed"
    exit 1
fi
echo "[sing-box] Configuration valid"

# Show enabled inbounds
INBOUNDS=$(grep -o '"tag"[[:space:]]*:[[:space:]]*"[^"]*"' "$RUNTIME_CONFIG" | head -10 | sed 's/"tag"[[:space:]]*:[[:space:]]*//g' | tr -d '"' | tr '\n' ', ' | sed 's/,$//')
echo "[sing-box] Inbounds: $INBOUNDS"

# Fix volume ownership (volumes may be root-owned from previous runs)
chown -R moav:moav /state /var/log/sing-box 2>/dev/null || true

# Copy certs to a moav-readable location (originals are root:root 600, volume is read-only)
if [ -d /certs/live ]; then
    for d in /certs/live/*/; do
        dir="/tmp/certs/live/$(basename "$d")"
        mkdir -p "$dir"
        cp -rL "$d"* "$dir/" 2>/dev/null || true
    done
fi
if [ -d /certs/selfsigned ]; then
    mkdir -p /tmp/certs/selfsigned
    cp -rL /certs/selfsigned/* /tmp/certs/selfsigned/ 2>/dev/null || true
fi
chown -R moav:moav /tmp/certs 2>/dev/null || true

# Rewrite cert paths in config to use the moav-readable copy
sed -i 's|/certs/|/tmp/certs/|g' "$RUNTIME_CONFIG"

# Run sing-box as non-root
echo "[sing-box] Starting proxy server..."
exec setpriv --reuid=moav --regid=moav --init-groups \
    --inh-caps=+net_admin,+net_bind_service \
    --ambient-caps=+net_admin,+net_bind_service \
    sing-box run -c "$RUNTIME_CONFIG"
