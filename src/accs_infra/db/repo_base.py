"""Shared database repository helpers."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from importlib import import_module
from typing import Any

from accs_infra.db.session import get_engine, session_scope


def _resolve(path: str) -> Callable[..., Any]:
    """Resolve a dotted ``path`` to a callable.

    Args:
        path: Dotted import path to resolve.

    Returns:
        The resolved callable.

    Raises:
        RuntimeError: If the module or attribute cannot be resolved.
    """
    module_path, _, attr = path.rpartition(".")
    if not module_path or not attr:
        raise RuntimeError(f"invalid import path: {path}")
    try:
        module = import_module(module_path)
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError(f"module not found: {module_path}") from exc
    try:
        return getattr(module, attr)
    except AttributeError as exc:  # pragma: no cover
        raise RuntimeError(f"attribute not found: {path}") from exc


class DBRepoBase:
    """Base class for repositories accessing the database.

    The class initialises an SQLAlchemy engine and provides utilities to resolve
    ACCScore helper functions and call them with optional connection injection.
    """

    _resolve = staticmethod(_resolve)

    def __init__(self, dsn: str | None = None) -> None:
        """Initialise repository with a database engine.

        Args:
            dsn: Optional database connection string. When ``None`` the
                configuration is loaded from :class:`accscore.settings.Settings`.
        """
        if dsn is None:
            from accscore.settings import Settings  # type: ignore[import-not-found]

            dsn = Settings().postgres_dsn
        self._engine = get_engine(dsn)

    def _call_with_optional_conn(
        self,
        func: Callable[..., Any],
        *args: Any,
        conn: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        """Call ``func`` injecting ``conn`` if its signature expects it."""
        sig = inspect.signature(func)
        if "conn" in sig.parameters and conn is not None and "conn" not in kwargs:
            kwargs["conn"] = conn
        return func(*args, **kwargs)

    def with_conn(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute ``func`` within a database session.

        The connection is injected if ``func`` accepts a ``conn`` keyword.
        """
        with session_scope(self._engine) as conn:
            return self._call_with_optional_conn(func, *args, conn=conn, **kwargs)
