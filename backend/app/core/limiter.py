"""Shared slowapi rate-limiter instance.

Import `limiter` in routers that need `@limiter.limit(...)` decorators.
Register it on the app in `main.py` via `app.state.limiter = limiter`.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
