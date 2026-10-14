"""Shared native aliases and validation helpers for the public API."""

from __future__ import annotations

import re

from ultralight_py import _native


def report_error(error: _native.UltralightError) -> None:
    _native._report_unraisable(error)


def validate_callable(value, name: str) -> None:
    if value is not None and not callable(value):
        raise TypeError(f"{name} must be callable or None")


def validate_dimension(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("View dimensions must be integers")
    if not 0 < value <= 0xFFFFFFFF:
        raise ValueError("View dimensions must be positive uint32 values")
    return value


def validate_session_name(name):
    if not isinstance(name, str):
        raise TypeError("Session name must be str")
    reserved = {"default", "con", "prn", "aux", "nul", "clock$", "conin$", "conout$"}
    reserved.update(f"{prefix}{number}" for prefix in ("com", "lpt") for number in range(1, 10))
    if not re.fullmatch(r"[a-z0-9_-]{1,80}", name) or name in reserved:
        raise ValueError("Invalid or reserved Session name")
    return name


def validate_bool(value, name):
    if type(value) is not bool:
        raise TypeError(f"{name} must be bool")
    return value
