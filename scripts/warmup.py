"""Crucible Free-Tier Keep-Alive Warmup Script.

Author: Arya Shah (Arya-A-Shah)
Script: scripts/warmup.py
"""

from __future__ import annotations

import os
import sys
import time
import urllib.request

DEFAULT_URL = "https://crucible-flexi-ca3.onrender.com/health"


def ping_service(url: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Crucible-Warmup/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.getcode()
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Warmup ping to {url}: HTTP {status}")
            return status == 200
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Warmup ping failed: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    target = os.getenv("RENDER_SERVICE_URL", DEFAULT_URL)
    ping_service(target)
