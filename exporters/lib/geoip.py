"""
GeoIP country lookup using DB-IP Lite or MaxMind GeoLite2 MMDB databases.

Gracefully degrades: if the database is missing, all lookups return "XX".
"""

import os

try:
    import maxminddb
except ImportError:
    maxminddb = None

DEFAULT_DB_PATH = "/geoip/dbip-country-lite.mmdb"


class GeoIPLookup:
    def __init__(self, db_path=None):
        self._reader = None
        self._path = db_path or os.environ.get("GEOIP_DB_PATH", DEFAULT_DB_PATH)
        self._load()

    def _load(self):
        if maxminddb is None:
            print("GeoIP: maxminddb not installed, country lookups disabled")
            return
        try:
            self._reader = maxminddb.open_database(self._path)
            print(f"GeoIP: loaded database from {self._path}")
        except Exception as e:
            print(f"GeoIP: could not load {self._path}: {e} (country lookups disabled)")

    def lookup(self, ip: str) -> str:
        """Return ISO 3166-1 alpha-2 country code, or 'XX' if unknown."""
        if not self._reader:
            return "XX"
        try:
            result = self._reader.get(ip)
            if result and "country" in result:
                return result["country"]["iso_code"]
            return "XX"
        except Exception:
            return "XX"
