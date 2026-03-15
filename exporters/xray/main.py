#!/usr/bin/env python3
"""
Xray User Prometheus Exporter

Parses Xray container logs for connection metrics and queries the
Xray Stats API (gRPC via dokodemo-door) for per-user traffic data.
"""

import json
import re
import time
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import defaultdict
from geoip import GeoIPLookup

# Metrics storage
user_connections = defaultdict(int)  # user -> total connections
user_last_seen = {}  # user -> timestamp
active_users = set()  # users seen in last 5 minutes
user_upload = defaultdict(int)  # user -> upload bytes (cumulative)
user_download = defaultdict(int)  # user -> download bytes (cumulative)
country_connections = defaultdict(int)  # country -> total connections
user_country = {}  # user -> last seen country code

# Lock for thread safety
metrics_lock = threading.Lock()

# GeoIP lookup
geoip = GeoIPLookup()

# Regex to parse Xray access log lines with source IP
# Format: IP:port accepted tcp:destination:port email:user@moav
IP_EMAIL_PATTERN = re.compile(
    r'(\d+\.\d+\.\d+\.\d+):\d+\s+accepted\s+.*?email:\s*(\S+?)@moav'
)
# Fallback patterns (without IP)
EMAIL_PATTERN = re.compile(r'email:\s*(\S+?)@moav')
BRACKET_PATTERN = re.compile(r'\[([^\]]+?)@moav\]')

# Active window in seconds (5 minutes)
ACTIVE_WINDOW = 300

# Stats query interval (seconds)
STATS_INTERVAL = 15

# Track first successful stats query for diagnostics
stats_query_count = 0


def parse_log_line(line: str) -> bool:
    """Parse a log line and update metrics. Returns True if parsed."""
    if 'accepted' not in line:
        return False

    source_ip = None
    username = None

    # Try to extract both IP and email
    ip_match = IP_EMAIL_PATTERN.search(line)
    if ip_match:
        source_ip = ip_match.group(1)
        username = ip_match.group(2)
    else:
        # Fallback: extract email only
        match = EMAIL_PATTERN.search(line)
        if not match:
            match = BRACKET_PATTERN.search(line)
        if not match:
            return False
        username = match.group(1)

    now = time.time()
    country = geoip.lookup(source_ip) if source_ip else "XX"

    with metrics_lock:
        user_connections[username] += 1
        user_last_seen[username] = now
        country_connections[country] += 1
        if source_ip:
            user_country[username] = country

    return True


def update_active_users():
    """Update the set of active users based on last seen time."""
    global active_users
    now = time.time()
    cutoff = now - ACTIVE_WINDOW

    with metrics_lock:
        active_users = {
            user for user, last_seen in user_last_seen.items()
            if last_seen > cutoff
        }


def query_xray_stats():
    """Query Xray Stats API for per-user cumulative traffic data."""
    try:
        result = subprocess.run(
            ['docker', 'exec', 'moav-xray', 'xray', 'api', 'statsquery',
             '-s', '127.0.0.1:10085', '-pattern', 'user'],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode != 0:
            result = subprocess.run(
                ['docker', 'exec', 'moav-xray', '/usr/local/bin/xray', 'api', 'statsquery',
                 '-s', '127.0.0.1:10085', '-pattern', 'user'],
                capture_output=True, text=True, timeout=10
            )

        if result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else "no stderr"
            print(f"Stats API error (rc={result.returncode}): {stderr}")
            return

        if stats_query_count == 0:
            print(f"Stats API raw: stdout={len(result.stdout)} bytes, stderr={len(result.stderr)} bytes")
            if result.stdout:
                print(f"Stats stdout preview: {result.stdout[:200]}")
            if result.stderr and not result.stdout:
                print(f"Stats stderr preview: {result.stderr[:200]}")

        # xray may output to stdout or stderr depending on version
        output = result.stdout.strip()
        if not output:
            output = result.stderr.strip()
        if not output:
            return

        parse_stats_output(output)

    except subprocess.TimeoutExpired:
        print("Stats API query timed out")
    except Exception as e:
        print(f"Stats API error: {e}")


def parse_stats_output(output: str):
    """Parse JSON stats output from xray api statsquery (cumulative values)."""
    global stats_query_count
    parsed_count = 0

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        stats_query_count += 1
        if stats_query_count <= 3:
            print(f"Stats query #{stats_query_count}: failed to parse JSON")
        return

    for entry in data.get("stat", []):
        name = entry.get("name", "")
        value = entry.get("value", 0)

        parts = name.split(">>>")
        if len(parts) == 4 and parts[0] == "user" and parts[2] == "traffic":
            username = parts[1].replace("@moav", "")
            direction = parts[3]

            with metrics_lock:
                if direction == "uplink":
                    user_upload[username] = value
                elif direction == "downlink":
                    user_download[username] = value
            parsed_count += 1

    stats_query_count += 1
    if stats_query_count <= 3 or stats_query_count % 100 == 0:
        total_up = sum(user_upload.values())
        total_down = sum(user_download.values())
        print(f"Stats query #{stats_query_count}: parsed {parsed_count} entries, "
              f"users with traffic: {len(user_upload)}, total: {total_up + total_down} bytes")


def tail_docker_logs():
    """Tail Xray container logs and parse user connections."""
    print("Starting log tailer for moav-xray...")

    while True:
        try:
            process = subprocess.Popen(
                ['docker', 'logs', '-f', '--tail', '100', 'moav-xray'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            for line in process.stdout:
                if 'accepted' in line and 'moav' in line:
                    if parse_log_line(line):
                        update_active_users()

            process.wait()
        except Exception as e:
            print(f"Error tailing logs: {e}")

        print("Log tailer disconnected, retrying in 5s...")
        time.sleep(5)


def periodic_update():
    """Periodically update active users and query stats API."""
    while True:
        time.sleep(STATS_INTERVAL)
        update_active_users()
        query_xray_stats()


class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler for Prometheus metrics endpoint."""

    def do_GET(self):
        if self.path == '/metrics':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()

            output = []

            with metrics_lock:
                # Active users count
                output.append('# HELP xray_active_users Number of users active in last 5 minutes')
                output.append('# TYPE xray_active_users gauge')
                output.append(f'xray_active_users {len(active_users)}')

                # Total unique users
                output.append('# HELP xray_total_users Total number of unique users seen')
                output.append('# TYPE xray_total_users counter')
                output.append(f'xray_total_users {len(user_connections)}')

                # Total connections
                output.append('# HELP xray_total_connections Total number of user connections')
                output.append('# TYPE xray_total_connections counter')
                output.append(f'xray_total_connections {sum(user_connections.values())}')

                # Per-user connections
                output.append('# HELP xray_user_connections Total connections per user')
                output.append('# TYPE xray_user_connections counter')
                for user, count in sorted(user_connections.items()):
                    output.append(f'xray_user_connections{{user="{user}"}} {count}')

                # Per-user active status
                output.append('# HELP xray_user_active Whether user is active (1) or inactive (0)')
                output.append('# TYPE xray_user_active gauge')
                for user in user_connections:
                    is_active = 1 if user in active_users else 0
                    output.append(f'xray_user_active{{user="{user}"}} {is_active}')

                # Per-user upload bytes
                output.append('# HELP xray_user_upload_bytes Total upload bytes per user')
                output.append('# TYPE xray_user_upload_bytes counter')
                for user, bytes_val in sorted(user_upload.items()):
                    output.append(f'xray_user_upload_bytes{{user="{user}"}} {bytes_val}')

                # Per-user download bytes
                output.append('# HELP xray_user_download_bytes Total download bytes per user')
                output.append('# TYPE xray_user_download_bytes counter')
                for user, bytes_val in sorted(user_download.items()):
                    output.append(f'xray_user_download_bytes{{user="{user}"}} {bytes_val}')

                # Total upload/download
                total_up = sum(user_upload.values())
                total_down = sum(user_download.values())
                output.append('# HELP xray_upload_bytes_total Total upload bytes across all users')
                output.append('# TYPE xray_upload_bytes_total counter')
                output.append(f'xray_upload_bytes_total {total_up}')

                output.append('# HELP xray_download_bytes_total Total download bytes across all users')
                output.append('# TYPE xray_download_bytes_total counter')
                output.append(f'xray_download_bytes_total {total_down}')

                # Connections by country
                output.append('# HELP xray_connections_by_country Total connections by source country')
                output.append('# TYPE xray_connections_by_country counter')
                for country, count in sorted(country_connections.items()):
                    output.append(f'xray_connections_by_country{{country="{country}"}} {count}')

                # Active users by country
                output.append('# HELP xray_active_users_by_country Active users by source country')
                output.append('# TYPE xray_active_users_by_country gauge')
                active_country_counts = defaultdict(int)
                for user in active_users:
                    c = user_country.get(user, "XX")
                    active_country_counts[c] += 1
                for country, count in sorted(active_country_counts.items()):
                    output.append(f'xray_active_users_by_country{{country="{country}"}} {count}')

            self.wfile.write('\n'.join(output).encode())

        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def main():
    port = 9103

    # Start log tailer in background thread
    tailer_thread = threading.Thread(target=tail_docker_logs, daemon=True)
    tailer_thread.start()

    # Start periodic update thread (active users + stats API)
    update_thread = threading.Thread(target=periodic_update, daemon=True)
    update_thread.start()

    # Start HTTP server
    server = HTTPServer(('0.0.0.0', port), MetricsHandler)
    print(f"Xray user exporter listening on port {port}")
    print(f"Metrics available at http://localhost:{port}/metrics")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == '__main__':
    main()
