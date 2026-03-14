#!/usr/bin/env python3
"""
Telemt API Prometheus Exporter

Polls the telemt REST API for operational data not available via built-in
Prometheus metrics: ME pool health, per-DC stats, upstream quality, gates
status, and NAT/STUN info.

API docs: https://github.com/telemt/telemt/blob/main/docs/API.md
"""

import json
import os
import time
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler

# Config
TELEMT_API = os.environ.get("TELEMT_API_URL", "http://telemt:9091")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "15"))

# Metrics storage
metrics_lock = threading.Lock()
metrics = {}


def safe_get(url, timeout=5):
    """Fetch JSON from telemt API, return dict or None on error."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            if data.get("ok"):
                return data.get("data", {})
    except Exception:
        pass
    return None


def poll_telemt_api():
    """Poll telemt API endpoints and build Prometheus metrics."""
    while True:
        new_metrics = {}

        # --- Health ---
        health = safe_get(f"{TELEMT_API}/v1/health")
        if health is not None:
            new_metrics["telemt_api_up"] = ("gauge", "Telemt API reachable", 1)
            new_metrics["telemt_api_read_only"] = (
                "gauge", "API is in read-only mode",
                1 if health.get("read_only") else 0
            )
        else:
            new_metrics["telemt_api_up"] = ("gauge", "Telemt API reachable", 0)

        # --- Gates (accepting connections?) ---
        gates = safe_get(f"{TELEMT_API}/v1/runtime/gates")
        if gates:
            new_metrics["telemt_api_gate_accepting"] = (
                "gauge", "Whether telemt is accepting client connections",
                1 if gates.get("client_gate_open", gates.get("accepting", True)) else 0
            )
            new_metrics["telemt_api_gate_me_ready"] = (
                "gauge", "Whether ME connections are established",
                1 if gates.get("me_ready", True) else 0
            )

        # --- ME Pool State ---
        pool = safe_get(f"{TELEMT_API}/v1/runtime/me_pool_state")
        if pool:
            new_metrics["telemt_api_pool_generation"] = (
                "gauge", "Current pool generation number",
                pool.get("generation", 0)
            )
            new_metrics["telemt_api_pool_writers_alive"] = (
                "gauge", "Number of alive ME writers",
                pool.get("writers_alive", pool.get("active_writers", 0))
            )
            new_metrics["telemt_api_pool_writers_draining"] = (
                "gauge", "Number of draining ME writers",
                pool.get("writers_draining", pool.get("draining_writers", 0))
            )
            new_metrics["telemt_api_pool_hardswap_active"] = (
                "gauge", "Whether a hardswap is in progress",
                1 if pool.get("hardswap_in_progress", False) else 0
            )

        # --- ME Quality ---
        quality = safe_get(f"{TELEMT_API}/v1/runtime/me_quality")
        if quality:
            new_metrics["telemt_api_me_route_drops"] = (
                "gauge", "Total ME route drop count",
                quality.get("route_drops", quality.get("route_drop_count", 0))
            )
            # Per-DC RTT if available
            dc_rtts = quality.get("dc_rtt", quality.get("dc_rtts", {}))
            if isinstance(dc_rtts, dict):
                for dc, rtt in dc_rtts.items():
                    key = f'telemt_api_dc_rtt_ms{{dc="{dc}"}}'
                    new_metrics[key] = (
                        "gauge", "RTT to Telegram DC in milliseconds",
                        rtt if isinstance(rtt, (int, float)) else 0
                    )

        # --- Upstream Quality ---
        upstream = safe_get(f"{TELEMT_API}/v1/runtime/upstream_quality")
        if upstream:
            upstreams = upstream.get("upstreams", upstream.get("endpoints", []))
            if isinstance(upstreams, list):
                for i, ep in enumerate(upstreams):
                    addr = ep.get("address", ep.get("addr", f"upstream_{i}"))
                    fails = ep.get("fail_count", ep.get("failures", 0))
                    latency = ep.get("latency_ms", ep.get("rtt_ms", 0))
                    key_fail = f'telemt_api_upstream_failures{{upstream="{addr}"}}'
                    key_lat = f'telemt_api_upstream_latency_ms{{upstream="{addr}"}}'
                    new_metrics[key_fail] = ("gauge", "Upstream failure count", fails)
                    new_metrics[key_lat] = ("gauge", "Upstream latency ms", latency)
            elif isinstance(upstreams, dict):
                for addr, info in upstreams.items():
                    fails = info.get("fail_count", info.get("failures", 0)) if isinstance(info, dict) else 0
                    latency = info.get("latency_ms", info.get("rtt_ms", 0)) if isinstance(info, dict) else 0
                    key_fail = f'telemt_api_upstream_failures{{upstream="{addr}"}}'
                    key_lat = f'telemt_api_upstream_latency_ms{{upstream="{addr}"}}'
                    new_metrics[key_fail] = ("gauge", "Upstream failure count", fails)
                    new_metrics[key_lat] = ("gauge", "Upstream latency ms", latency)

        # --- DC Stats ---
        dcs = safe_get(f"{TELEMT_API}/v1/stats/dcs")
        if dcs:
            dc_list = dcs if isinstance(dcs, dict) else {}
            # Handle both dict and list formats
            if isinstance(dcs, list):
                dc_list = {d.get("dc", d.get("id", i)): d for i, d in enumerate(dcs)}
            for dc_id, info in dc_list.items():
                if isinstance(info, dict):
                    avail = info.get("availability_pct", info.get("availability", 0))
                    writers = info.get("writers", info.get("writer_count", 0))
                    key_avail = f'telemt_api_dc_availability_pct{{dc="{dc_id}"}}'
                    key_writers = f'telemt_api_dc_writers{{dc="{dc_id}"}}'
                    new_metrics[key_avail] = ("gauge", "DC availability percentage", avail)
                    new_metrics[key_writers] = ("gauge", "Writers connected to DC", writers)

        # --- NAT/STUN ---
        stun = safe_get(f"{TELEMT_API}/v1/runtime/nat_stun")
        if stun:
            # Map NAT type to numeric (0=unknown, 1=open, 2=full_cone, 3=restricted, 4=symmetric)
            nat_map = {"unknown": 0, "open": 1, "full_cone": 2, "restricted": 3,
                       "port_restricted": 3, "symmetric": 4}
            nat_type = stun.get("nat_type", stun.get("nat", "unknown"))
            if isinstance(nat_type, str):
                nat_type = nat_map.get(nat_type.lower(), 0)
            new_metrics["telemt_api_nat_type"] = (
                "gauge", "NAT type (0=unknown 1=open 2=full_cone 3=restricted 4=symmetric)",
                nat_type
            )
            new_metrics["telemt_api_stun_ok"] = (
                "gauge", "Whether STUN detection succeeded",
                1 if stun.get("stun_ok", stun.get("detected", False)) else 0
            )

        # --- Connection Summary ---
        conns = safe_get(f"{TELEMT_API}/v1/runtime/connections/summary")
        if conns:
            new_metrics["telemt_api_connections_current"] = (
                "gauge", "Current active connections from API",
                conns.get("current", conns.get("active", 0))
            )

        with metrics_lock:
            metrics.update(new_metrics)

        time.sleep(POLL_INTERVAL)


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return

        with metrics_lock:
            current = dict(metrics)

        lines = []
        seen_help = set()
        for key, (mtype, help_text, value) in sorted(current.items()):
            # Extract base metric name (without labels)
            base = key.split("{")[0]
            if base not in seen_help:
                lines.append(f"# HELP {base} {help_text}")
                lines.append(f"# TYPE {base} {mtype}")
                seen_help.add(base)
            lines.append(f"{key} {value}")

        output = "\n".join(lines) + "\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.end_headers()
        self.wfile.write(output.encode())

    def log_message(self, format, *args):
        pass  # Suppress request logging


def main():
    print(f"Telemt API exporter starting (polling {TELEMT_API} every {POLL_INTERVAL}s)")
    print(f"Serving metrics on :9104/metrics")

    poller = threading.Thread(target=poll_telemt_api, daemon=True)
    poller.start()

    server = HTTPServer(("0.0.0.0", 9104), MetricsHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
