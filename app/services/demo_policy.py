"""Demo vs real incentive visibility for search and listings."""

from __future__ import annotations

from app.config import get_settings


def resolve_include_demo(include_demo: bool | None) -> bool:
    """
    Query param overrides env default.

    SHOW_DEMO_DATA=true (default locally): include demo unless include_demo=false.
    SHOW_DEMO_DATA=false (production): exclude demo unless include_demo=true.
    """
    if include_demo is not None:
        return include_demo
    return get_settings().show_demo_data
