"""Reusable Python exports installed into each attached View's main document."""

from __future__ import annotations

import re

from typing_extensions import Self

from ultralight_py import _native, _objects, _support
from ultralight_py import api as _api


def validate_name(name):
    if not isinstance(name, str):
        raise TypeError("API names must be str")
    if not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", name):
        raise ValueError("API names must be JavaScript identifiers")
    return name


class API:
    """Register independently of Views; detach revokes existing document proxies.

    Definitions survive navigation and the closure of the last attached View.
    Close the API explicitly to release the registered Python objects.
    """

    def __init__(self, namespace):
        _support.ensure_in_main_thread()
        validate_name(namespace)
        if namespace in {"Python", "ul", "ultralight"}:
            raise ValueError("Reserved API namespace")
        self._namespace = namespace
        self._native = _native._API(namespace)

    @property
    def namespace(self):
        return self._namespace

    @property
    def closed(self):
        return self._native.closed

    def register(self, callback=None, *, name=None):
        """Register a callable directly or as a decorator, returning it unchanged."""
        _support.call(self._native.check)
        if name is not None:
            validate_name(name)
        if callback is None:
            return lambda function: self.register(function, name=name)
        if not callable(callback):
            raise TypeError("callback must be callable")
        label = name if name is not None else getattr(callback, "__name__", None)
        self.register_object(label, callback)
        return callback

    def register_object(self, name, instance, *, members=None):
        _support.call(self._native.check)
        validate_name(name)
        if members is not None:
            if isinstance(members, str):
                raise TypeError("members must be a sequence of public names")
            members = tuple(members)
            if any(not isinstance(member, str) or member.startswith("_") for member in members):
                raise ValueError("members must contain public names")
            if set(members) - set(_objects.members(instance)):
                raise ValueError("members contains an unknown Python member")
        _support.call(self._native.register, name, instance, members)

    def unregister(self, name):
        _support.call(self._native.unregister, validate_name(name))

    def attach(self, view):
        if not isinstance(view, _api.View):
            raise TypeError("view must be View")
        _support.call(self._native.attach, view._native)

    def detach(self, view):
        if not isinstance(view, _api.View):
            raise TypeError("view must be View")
        _support.call(self._native.detach, view._native)

    def close(self):
        _support.call(self._native.close)

    def __enter__(self) -> Self:
        _support.call(self._native.check)
        return self

    def __exit__(self, *exc):
        self.close()
