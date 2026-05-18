"""Unified entry point for the MLOps container.

Sub-commands::

    python -m mlops scheduler            # run periodic AutoML + drift cycles
    python -m mlops scheduler --once     # one-shot AutoML cycle then exit
    python -m mlops api                  # uvicorn FastAPI server
    python -m mlops collector            # legacy data collector (sensor_collector.py)
    python -m mlops automl  [args...]    # delegate to mlops.training.automl CLI
    python -m mlops deploy  [args...]    # delegate to mlops.deployment.edge_deployer CLI

The same image is used for ``mlops_scheduler`` and ``mlops_api`` services in
docker-compose; the only thing that changes is the command.
"""

from __future__ import annotations

import argparse
import logging
import sys

import structlog


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.stdlib.LoggerFactory(),
    )


def _cmd_scheduler(rest: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="mlops scheduler")
    parser.add_argument("--once", action="store_true", help="Run one cycle then exit")
    parser.add_argument("--cycle", choices=["automl", "drift"], default="automl")
    args = parser.parse_args(rest)

    from mlops.orchestrator.scheduler import OrchestratorScheduler

    scheduler = OrchestratorScheduler()
    if args.once:
        if args.cycle == "drift":
            scheduler.run_drift_cycle()
        else:
            scheduler.run_automl_cycle()
        return 0

    scheduler.run_forever()
    return 0


def _cmd_api(rest: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="mlops api")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args(rest)

    import uvicorn

    from mlops.config import get_settings

    settings = get_settings()
    uvicorn.run(
        "mlops.api.server:app",
        host=args.host or settings.api_host,
        port=args.port or settings.api_port,
        log_level="info",
    )
    return 0


def _cmd_collector(rest: list[str]) -> int:
    from mlops.data_collector import sensor_collector  # noqa: F401

    # The legacy module runs its own main when imported as __main__.
    import runpy

    runpy.run_module("mlops.data_collector.sensor_collector", run_name="__main__")
    return 0


def _cmd_passthrough(module: str, rest: list[str]) -> int:
    """Delegate to an existing module's CLI with its own argparse."""
    import runpy

    sys.argv = [module, *rest]
    runpy.run_module(module, run_name="__main__")
    return 0


_COMMANDS = {
    "scheduler": _cmd_scheduler,
    "api": _cmd_api,
    "collector": _cmd_collector,
}


def main() -> int:
    _configure_logging()

    parser = argparse.ArgumentParser(prog="python -m mlops", add_help=False)
    parser.add_argument(
        "command",
        nargs="?",
        choices=[*_COMMANDS, "automl", "deploy", "help", "--help", "-h"],
        default="help",
    )
    args, rest = parser.parse_known_args()

    if args.command in ("help", "--help", "-h", None):
        print(__doc__)
        return 0

    if args.command == "automl":
        return _cmd_passthrough("mlops.training.automl", rest)
    if args.command == "deploy":
        return _cmd_passthrough("mlops.deployment.edge_deployer", rest)

    return _COMMANDS[args.command](rest)


if __name__ == "__main__":
    sys.exit(main())
