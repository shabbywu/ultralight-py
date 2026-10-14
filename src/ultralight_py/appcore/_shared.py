"""Validation helpers shared by AppCore windows and applications."""

from __future__ import annotations

import math


def dimension(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Window dimensions must be numbers")
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Window dimensions must be finite and positive")
    return value


def text(value, name):
    if not isinstance(value, str):
        raise TypeError(f"{name} must be str")
    if "\0" in value:
        raise ValueError(f"{name} cannot contain NUL")
    return value
