#!/usr/bin/env python3
"""
Sing-box User Prometheus Exporter

Parses sing-box container logs to extract user connection metrics.
Log format: ... inbound/protocol[tag]: [username] inbound connection from IP:port
"""

import re
import time
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import defaultdict
from datetime import datetime
from geoip import GeoIPLookup

# Metrics storage
user_connections = defaultdict(int)  # user -> total connections
user_last_seen = {}  # user -> timestamp
active_users = set()  # users seen in last 5 minutes
protocol_connections = defaultdict(int)  # protocol -> total connections
country_connections = defaultdict(int)  # country -> total connections
user_country = {}  # user -> last seen country code

# Lock for thread safety
metrics_lock = threading.Lock()

# GeoIP lookup
geoip = GeoIPLookup()

# Regex to parse connection lines with usernames and source IP
# Example: inbound/hysteria2[hysteria2-in]: [user] inbound connection from 1.2.3.4:12345
USER_IP_PATTERN = re.compile(
    r'\[([^\]]+)\]\s*inbound connection(?:\s+from\s+(\d+\.\d+\.\d+\.\d+))?'
)

# Regex to extract protocol from inbound name
# Example: inbound/hysteria2[hysteria2-in]: [user]
PROTOCOL_PATTERN = re.compile(r'inbound/(\w+)\[')

# Active window in seconds (5 minutes)
ACTIVE_WINDOW = 300

def parse_log_line(line: str) -> bool:
    """Parse a log line and update metrics. Returns True if parsed."""
    user_match = USER_IP_PATTERN.search(line)
    if not user_match:
        return False

    username = user_match.group(1)
    source_ip = user_match.group(2)  # may be None
    now = time.time()

    # Extract protocol if present
    protocol_match = PROTOCOL_PATTERN.search(line)
    protocol = protocol_match.group(1) if protocol_match else "unknown"

    # GeoIP lookup
    country = geoip.lookup(source_ip) if source_ip else "XX"

    with metrics_lock:
        user_connections[username] += 1
        user_last_seen[username] = now
        protocol_connections[protocol] += 1
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

def tail_docker_logs():
    """Tail sing-box container logs and parse user connections."""
    print("Starting log tailer for moav-sing-box...")

    while True:
        try:
            process = subprocess.Popen(
                ['docker', 'logs', '-f', '--tail', '100', 'moav-sing-box'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            for line in process.stdout:
                if 'inbound connection' in line and '[' in line:
                    if parse_log_line(line):
                        update_active_users()

            process.wait()
        except Exception as e:
            print(f"Error tailing logs: {e}")

        print("Log tailer disconnected, retrying in 5s...")
        time.sleep(5)

def periodic_update():
    """Periodically update active users set."""
    while True:
        time.sleep(60)
        update_active_users()

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
                output.append('# HELP singbox_active_users Number of users active in last 5 minutes')
                output.append('# TYPE singbox_active_users gauge')
                output.append(f'singbox_active_users {len(active_users)}')

                # Total unique users
                output.append('# HELP singbox_total_users Total number of unique users seen')
                output.append('# TYPE singbox_total_users counter')
                output.append(f'singbox_total_users {len(user_connections)}')

                # Total connections
                output.append('# HELP singbox_total_connections Total number of user connections')
                output.append('# TYPE singbox_total_connections counter')
                output.append(f'singbox_total_connections {sum(user_connections.values())}')

                # Per-user connections
                output.append('# HELP singbox_user_connections Total connections per user')
                output.append('# TYPE singbox_user_connections counter')
                for user, count in sorted(user_connections.items()):
                    output.append(f'singbox_user_connections{{user="{user}"}} {count}')

                # Per-user active status
                output.append('# HELP singbox_user_active Whether user is active (1) or inactive (0)')
                output.append('# TYPE singbox_user_active gauge')
                for user in user_connections:
                    is_active = 1 if user in active_users else 0
                    output.append(f'singbox_user_active{{user="{user}"}} {is_active}')

                # Per-protocol connections
                output.append('# HELP singbox_protocol_connections Total connections per protocol')
                output.append('# TYPE singbox_protocol_connections counter')
                for protocol, count in sorted(protocol_connections.items()):
                    output.append(f'singbox_protocol_connections{{protocol="{protocol}"}} {count}')

                # Connections by country
                output.append('# HELP singbox_connections_by_country Total connections by source country')
                output.append('# TYPE singbox_connections_by_country counter')
                for country, count in sorted(country_connections.items()):
                    output.append(f'singbox_connections_by_country{{country="{country}"}} {count}')

                # Active users by country
                output.append('# HELP singbox_active_users_by_country Active users by source country')
                output.append('# TYPE singbox_active_users_by_country gauge')
                active_country_counts = defaultdict(int)
                for user in active_users:
                    c = user_country.get(user, "XX")
                    active_country_counts[c] += 1
                for country, count in sorted(active_country_counts.items()):
                    output.append(f'singbox_active_users_by_country{{country="{country}"}} {count}')

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
    port = 9102

    # Start log tailer in background thread
    tailer_thread = threading.Thread(target=tail_docker_logs, daemon=True)
    tailer_thread.start()

    # Start periodic update thread
    update_thread = threading.Thread(target=periodic_update, daemon=True)
    update_thread.start()

    # Start HTTP server
    server = HTTPServer(('0.0.0.0', port), MetricsHandler)
    print(f"Sing-box user exporter listening on port {port}")
    print(f"Metrics available at http://localhost:{port}/metrics")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()

if __name__ == '__main__':
    main()
