#!/usr/bin/env python3
"""Inspect sing-box connections from logs with GeoIP country lookup.
This script is run INSIDE the singbox-exporter container via docker exec."""

import sys, os, re, json
from collections import Counter, defaultdict

filter_country = os.environ.get("FILTER", "").upper()
json_mode = os.environ.get("JSON_MODE", "") == "true"
since = os.environ.get("SINCE", "6h")

sys.path.insert(0, "/app")
try:
    from geoip import GeoIPLookup
    geo = GeoIPLookup()
except Exception:
    geo = None
    print("WARNING: GeoIP not available", file=sys.stderr)

def lookup(ip):
    if not ip or not geo:
        return "??"
    try:
        return geo.lookup(ip)
    except:
        return "??"

conn_id_re = re.compile(r'\[(\d{5,}) ')
src_ip_re = re.compile(r'(?:inbound|process) connection from (\d+\.\d+\.\d+\.\d+):\d+')
dest_re = re.compile(r'inbound connection to ([^\s]+)')
user_re = re.compile(r'\[([a-zA-Z0-9_-]+)\] inbound connection to')
inbound_re = re.compile(r'inbound/\w+\[([^\]]+)\]')
outbound_re = re.compile(r'outbound connection to ([^\s]+)')

conn_source = {}
conn_dest = {}
conn_user = {}
conn_inbound = {}
conn_error = set()

# Strip ANSI escape codes (sing-box logs include color codes)
ansi_re = re.compile(r'\x1b\[[0-9;]*m')

# Read from mounted log file or stdin
logfile = os.environ.get("LOGFILE", "")
if logfile and os.path.exists(logfile):
    source = open(logfile, "r")
else:
    source = sys.stdin

for raw_line in source:
    line = ansi_re.sub("", raw_line).strip()
    cid_match = conn_id_re.search(line)
    if not cid_match:
        continue
    cid = cid_match.group(1)

    src_match = src_ip_re.search(line)
    if src_match:
        ip = src_match.group(1)
        if not (ip.startswith("10.") or ip.startswith("172.") or ip.startswith("127.")):
            conn_source[cid] = ip

    ib_match = inbound_re.search(line)
    if ib_match:
        conn_inbound[cid] = ib_match.group(1)

    dest_match = dest_re.search(line)
    if dest_match:
        conn_dest[cid] = dest_match.group(1)

    user_match = user_re.search(line)
    if user_match:
        conn_user[cid] = user_match.group(1)

    out_match = outbound_re.search(line)
    if out_match and cid not in conn_dest:
        conn_dest[cid] = out_match.group(1)

    if "ERROR" in line:
        conn_error.add(cid)

all_src_ips = set(conn_source.values())
ip_country = {ip: lookup(ip) for ip in all_src_ips}

if filter_country:
    valid_ips = set(ip for ip, cc in ip_country.items() if cc == filter_country)
else:
    valid_ips = all_src_ips

ip_stats = defaultdict(lambda: {
    "conns": 0, "errors": 0, "country": "??",
    "inbounds": Counter(), "users": Counter(), "destinations": Counter()
})

for cid, src_ip in conn_source.items():
    if src_ip not in valid_ips:
        continue
    stats = ip_stats[src_ip]
    stats["conns"] += 1
    stats["country"] = ip_country.get(src_ip, "??")
    if cid in conn_error:
        stats["errors"] += 1
    if cid in conn_inbound:
        stats["inbounds"][conn_inbound[cid]] += 1
    if cid in conn_user:
        stats["users"][conn_user[cid]] += 1
    if cid in conn_dest:
        stats["destinations"][conn_dest[cid]] += 1

total_entries = sum(s["conns"] for s in ip_stats.values())

if json_mode:
    out = {}
    for ip, s in ip_stats.items():
        out[ip] = {
            "country": s["country"], "conns": s["conns"], "errors": s["errors"],
            "users": dict(s["users"]),
            "destinations": dict(s["destinations"].most_common(20)),
            "inbounds": dict(s["inbounds"])
        }
    json.dump({"filter": filter_country or "all", "since": since, "ips": out}, sys.stdout, indent=2)
    print()
    sys.exit(0)

label = " from %s" % filter_country if filter_country else ""
print("")
print("  Connections%s (last %s)" % (label, since))
print("  Log entries: %d | Unique IPs: %d" % (total_entries, len(ip_stats)))
print("")

if not ip_stats:
    print("  No connections%s found." % label)
    print("")
    sys.exit(0)

countries = Counter()
for s in ip_stats.values():
    countries[s["country"]] += s["conns"]
print("  Countries:")
for c, n in countries.most_common():
    print("    %s: %d" % (c, n))

inbounds = Counter()
for s in ip_stats.values():
    inbounds.update(s["inbounds"])
if inbounds:
    print("")
    print("  Inbounds:")
    for i, n in inbounds.most_common():
        print("    %s: %d" % (i, n))

users = Counter()
for s in ip_stats.values():
    users.update(s["users"])
if users:
    print("")
    print("  Users:")
    for u, n in users.most_common(15):
        print("    %s: %d" % (u, n))

all_dests = Counter()
for s in ip_stats.values():
    all_dests.update(s["destinations"])
if all_dests:
    print("")
    print("  Top destinations:")
    for d, n in all_dests.most_common(30):
        print("    %s: %d" % (d, n))

print("")
print("  Source IPs: %d unique" % len(ip_stats))
print("  %-18s %-4s %8s %8s  %-14s %s" % ("IP", "CC", "Conns", "Errors", "User", "Top Destinations"))
print("  " + "-" * 100)
for ip, info in sorted(ip_stats.items(), key=lambda x: -x[1]["conns"]):
    top_user = info["users"].most_common(1)[0][0] if info["users"] else "-"
    top_dests = ", ".join(d for d, _ in info["destinations"].most_common(3))
    if not top_dests:
        top_dests = "(no dest logged)"
    print("  %-18s %-4s %8d %8d  %-14s %s" % (
        ip, info["country"], info["conns"], info["errors"], top_user, top_dests))
print("")
