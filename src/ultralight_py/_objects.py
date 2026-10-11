"""Internal member policy and operators for live Python proxies."""

from __future__ import annotations

import inspect
import operator
import types

from ultralight_py import api as _api


def members(value, allowed=None):
    names = set()
    for cls in type.__getattribute__(type(value), "__mro__"):
        names.update(type.__getattribute__(cls, "__dict__"))
    descriptor = inspect.getattr_static(value, "__dict__", None)
    namespace = {}
    if isinstance(descriptor, types.GetSetDescriptorType):
        try:
            namespace = object.__getattribute__(value, "__dict__")
        except (AttributeError, TypeError):
            pass
    if isinstance(namespace, dict):
        names.update(namespace)
    names = {name for name in names if isinstance(name, str) and not name.startswith("_")}
    if allowed is not None:
        names.intersection_update(allowed)
    return sorted(names)


def identity(value):
    if isinstance(value, types.MethodType):
        return ("method", id(value.__self__), id(value.__func__))
    if isinstance(value, types.BuiltinMethodType) and value.__self__ is not None:
        return ("builtin", id(value.__self__), value.__name__)
    return ("object", id(value))


def unwrap(value):
    return value._native if isinstance(value, _api.JSValue) else value


def validate(value):
    if isinstance(value, (type, types.ModuleType, bytes, bytearray, memoryview)):
        raise TypeError("Classes, modules and binary buffers cannot be exported as Python proxies")
    if inspect.isawaitable(value):
        # A freshly returned coroutine cannot be consumed by synchronous JS.
        if inspect.iscoroutine(value):
            value.close()
        raise TypeError("Awaitables require an async bridge")


def member(value, name, allowed):
    if not isinstance(name, str) or name not in members(value, allowed):
        raise AttributeError(f"Python member {name!r} is not exposed")
    return getattr(value, name)


def set_member(value, name, item, allowed):
    if not isinstance(name, str) or name not in members(value, allowed):
        raise AttributeError(f"Python member {name!r} is not exposed")
    descriptor = inspect.getattr_static(value, name)
    if callable(descriptor) or isinstance(descriptor, (staticmethod, classmethod)):
        raise AttributeError(f"Python method {name!r} is read-only")
    if isinstance(descriptor, property) and descriptor.fset is None:
        raise AttributeError(f"Python property {name!r} is read-only")
    setattr(value, name, item)


def operate(name, args):
    if name == "getitem":
        return operator.getitem(*args)
    if name == "setitem":
        operator.setitem(*args)
        return None
    if name == "delitem":
        operator.delitem(*args)
        return None
    if name == "len":
        return len(*args)
    if name == "contains":
        return operator.contains(*args)
    if name == "slice":
        return slice(*args)
    if name == "call":
        fn, positional, *keywords = args
        return fn(*positional, **(keywords[0] if keywords else {}))
    raise ValueError(f"Unknown Python operator: {name}")
