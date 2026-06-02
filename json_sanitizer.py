#!/usr/bin/env python3
"""
Shared JSON sanitizer — prevents NaN/Infinity from reaching JSON output.

Import and use ``sanitize()`` on any data structure before ``json.dumps()``,
or use ``safe_json_dumps()`` as a drop-in replacement.

NaN and Infinity are NOT valid JSON tokens. If they end up in a .json file,
``JSON.parse()`` in browsers will throw, breaking the entire dashboard.
"""

import json
import math
from typing import Any


def sanitize(obj: Any) -> Any:
    """
    Recursively replace NaN/Infinity with None (which json.dumps writes as ``null``).

    Handles floats, lists, dicts, and nested structures.
    Returns a new object (does not mutate the input for dicts/lists).
    """
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    return obj


def safe_json_dumps(obj: Any, **kwargs) -> str:
    """
    Drop-in replacement for ``json.dumps()`` that sanitizes NaN/Infinity first.

    Accepts all the same kwargs (``indent``, ``ensure_ascii``, etc.).
    """
    clean = sanitize(obj)
    return json.dumps(clean, **kwargs)


def safe_json_dump(obj: Any, fp, **kwargs) -> None:
    """
    Drop-in replacement for ``json.dump()`` that sanitizes NaN/Infinity first.
    """
    clean = sanitize(obj)
    return json.dump(clean, fp, **kwargs)


__all__ = ["sanitize", "safe_json_dumps", "safe_json_dump"]
