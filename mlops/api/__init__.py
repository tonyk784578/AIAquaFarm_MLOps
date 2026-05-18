"""MLOps FastAPI service — read-only observability + service-key-gated admin actions.

Run::

    python -m mlops api               # uvicorn on $MLOPS_API_HOST:$MLOPS_API_PORT
"""

from mlops.api.server import create_app

__all__ = ["create_app"]
