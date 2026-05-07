"""Service health check — verifies all AIAquafarm services are running.

Usage:
    python scripts/health_check.py
    # or
    make health
"""

import sys
from typing import Optional

import httpx

SERVICES = [
    ("Backend API",   "http://localhost:8000/health"),
    ("Dashboard",     "http://localhost/health"),
    ("MLflow",        "http://localhost:5000/health"),
]

BOLD  = "\033[1m"
GREEN = "\033[0;32m"
RED   = "\033[0;31m"
RESET = "\033[0m"


def check(name: str, url: str, timeout: float = 5.0) -> bool:
    """Send a GET request and check for 200 OK.

    Args:
        name: Human-readable service name.
        url: Health check URL.
        timeout: Request timeout in seconds.

    Returns:
        True if service is healthy.
    """
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        if resp.status_code == 200:
            print(f"  {GREEN}✓{RESET} {name}")
            return True
        else:
            print(f"  {RED}✗{RESET} {name} — HTTP {resp.status_code}")
            return False
    except httpx.RequestError as exc:
        print(f"  {RED}✗{RESET} {name} — {exc}")
        return False


def main() -> int:
    print(f"\n{BOLD}AIAquafarm Service Health Check{RESET}\n")
    results = [check(name, url) for name, url in SERVICES]
    all_healthy = all(results)
    print()
    if all_healthy:
        print(f"{GREEN}{BOLD}All services healthy.{RESET}\n")
        return 0
    else:
        failed = sum(1 for r in results if not r)
        print(f"{RED}{BOLD}{failed} service(s) unhealthy.{RESET}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
