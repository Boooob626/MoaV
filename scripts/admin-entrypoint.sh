#!/bin/sh

# =============================================================================
# Admin dashboard entrypoint with logging
# =============================================================================

echo "[admin] Starting MoaV Admin Dashboard"
echo "[admin] Port: 8443"

# Copy certs to a moav-readable location (originals are root:root 600, volume is read-only)
mkdir -p /tmp/certs/selfsigned
cp -rL /certs/selfsigned/* /tmp/certs/selfsigned/ 2>/dev/null || true
for d in /certs/live/*/; do
    dir="/tmp/certs/live/$(basename "$d")"
    mkdir -p "$dir"
    cp -rL "$d"* "$dir/" 2>/dev/null || true
done
chown -R moav:moav /tmp/certs 2>/dev/null || true

# Check for SSL certificates
CERT_DIRS=$(find /certs/live -maxdepth 1 -type d 2>/dev/null | tail -n +2 | head -1)
if [ -n "$CERT_DIRS" ]; then
    echo "[admin] SSL: Enabled (found certificates)"
else
    echo "[admin] SSL: Disabled (no certificates found)"
fi

# Ensure required directories exist and are writable by moav user
# Use chmod 777 instead of chown — more reliable across Docker volume mount scenarios
mkdir -p /project/outputs/bundles /project/state/users /project/configs/amneziawg /project/configs/wireguard 2>/dev/null || true
chown -R moav:moav /project/outputs /project/configs /project/state 2>/dev/null || true
chmod -R a+rwX /project/outputs /project/state 2>/dev/null || true
chmod -R a+rwX /project/configs/sing-box /project/configs/xray /project/configs/amneziawg /project/configs/wireguard /project/configs/trusttunnel /project/configs/telemt 2>/dev/null || true

# Run the dashboard as non-root
echo "[admin] Starting uvicorn server..."
exec su-exec moav python main.py
