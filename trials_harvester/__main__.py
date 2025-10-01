"""Module entry point for :mod:`trials_harvester`."""

from __future__ import annotations

from .cli import main


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
