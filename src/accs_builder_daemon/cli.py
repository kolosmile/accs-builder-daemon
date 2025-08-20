"""Command line interface for the builder daemon."""

from __future__ import annotations

import argparse
import logging
import time

from accs_builder_daemon.domain.tick import tick
from accs_builder_daemon.repo.builder_repo import DefaultRepo

logger = logging.getLogger(__name__)


def main() -> None:
    """Entry point for the builder daemon."""
    parser = argparse.ArgumentParser("accs-builder")
    parser.add_argument(
        "--every", type=float, default=2.0, help="Seconds between ticks"
    )
    parser.add_argument(
        "--once", action="store_true", help="Run a single tick and exit"
    )
    parser.add_argument("--dsn", default=None, help="Database DSN override")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    dsn = args.dsn or None
    if dsn is None:
        from accscore.settings import Settings  # type: ignore[import-not-found]

        used_dsn = Settings().postgres_dsn
    else:
        used_dsn = dsn
    repo = DefaultRepo(dsn=dsn)

    def _mask_dsn(value: str) -> str:
        from urllib.parse import urlsplit

        parts = urlsplit(value)
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        return f"{parts.scheme}://***:***@{host}{parts.path}"

    logging.info("builder.start", extra={"dsn": _mask_dsn(used_dsn)})

    if args.once:
        tick(repo=repo)
        return

    interval = max(0.05, float(args.every))
    while True:
        try:
            tick(repo=repo)
        except Exception as exc:  # pragma: no cover
            logger.exception("builder.tick.failed: %s", exc)
        time.sleep(interval)


if __name__ == "__main__":
    main()
