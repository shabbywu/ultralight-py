"""Internal member policy and operators for live Python proxies."""

from __future__ import annotations

import inspect
import operator
import types

from ultralight_py import _native
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
    return (
        value._native if isinstance(value, (_api.JSValue, _api.JSArray, _api.JSObject)) else value
    )


def container(value, operation, args):
    """Data operations for array/object proxies, separate from member discovery."""
    if isinstance(value, list):
        if operation == "item_length":
            return len(value)
        if operation == "item_keys":
            return [str(i) for i in range(len(value))]
        if operation == "item_resize":
            length = int(args[0])  # JS accepts -0 as an Array length.
            if length < len(value):
                del value[length:]
            else:
                value.extend([_native.undefined] * (length - len(value)))
            return None
        index = int(args[0])
        if operation == "item_has":
            return 0 <= index < len(value)
        if operation == "item_get":
            return value[index] if index < len(value) else _native.undefined
        if operation == "item_set":
            if index >= len(value):
                value.extend([_native.undefined] * (index + 1 - len(value)))
            value[index] = args[1]
        elif operation == "item_delete":
            if index < len(value):
                value[index] = _native.undefined
        else:
            raise ValueError(f"Unknown container operation: {operation}")
        return None
    if operation == "item_keys":
        # Object property order: array indices first, then other string keys.
        keys = [key for key in value if isinstance(key, str)]
        indices = {
            key
            for key in keys
            if len(key) <= 10
            and key.isascii()
            and key.isdigit()
            and str(int(key)) == key
            and int(key) < 2**32 - 1
        }
        return sorted(indices, key=int) + [key for key in keys if key not in indices]
    key = args[0]
    if operation == "item_has":
        return key in value
    if operation == "item_get":
        return value.get(key, _native.undefined)
    if operation == "item_set":
        value[key] = args[1]
    elif operation == "item_delete":
        value.pop(key, None)
    else:
        raise ValueError(f"Unknown container operation: {operation}")
    return None


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
    read_only_method = callable(descriptor) or isinstance(descriptor, (staticmethod, classmethod))
    if read_only_method:
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
