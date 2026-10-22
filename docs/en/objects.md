# Python object bridging

After Python creates an ordinary instance, JS can directly access its public attributes and methods.
Python list/dict and JS Array/plain objects share references by default; changes on either side are visible on the next access from the other.
All bridge operations run on Python's main thread.

```python
class Counter:
    def __init__(self, value):
        self.value = value
        self.history = []

    def increment(self, amount=1):
        self.value += amount
        self.history.append(self.value)
        return self.value


left, right = Counter(0), Counter(100)
left_binding = view.bind_object("left", left)
right_binding = view.bind_object("right", right)
```

```javascript
left.value = 10;
left.increment(2);
right.increment(3);
const incrementLeft = left.increment;
incrementLeft.call(right, 1); // Still calls left: the Python method is bound.
```

To expose objects before inline scripts run, call `bind_object()` in the main-frame `window_ready` callback.
These document-level bindings must be recreated after main-frame navigation.
For automatic restoration, use the [standalone API registry](appcore.md#registration-and-restoration); object and container rules are identical.

## Members and identity

`bind_object(name, instance, *, members=None)` returns `PythonBinding`.
By default it discovers public members through the instance dictionary, `__slots__`, and the class method resolution order,
excluding underscore-prefixed names. For example, `members=["value", "increment"]` further restricts the root object's members.
Nested instances still follow the default public-member rules; the allowlist does not recursively restrict the entire object graph.

Attributes are read live; assignment follows Python `setattr` and property setters.
Writing read-only properties, methods, or unexposed members raises an error.
Reading an unknown member returns JS undefined; explicit `Python.getattr()` raises Python AttributeError.
`Object.keys()` and `in` only inspect member names without invoking property getters.
Dynamic members from `__getattr__` or `__dir__` are not discovered automatically.
Changing descriptors, changing prototypes, and freezing proxies from JS are unsupported.

Within one binding, a Python object maps to the same proxy, supporting `return self`, nested aliases, and cycles.
Different instances have separate proxy and bound-method caches; instance state is not placed on JS class prototypes.
Class attributes shared by Python remain shared; the bridge does not copy them.

Binding the same Python instance to two names creates proxies with different `===` identities that access the same Python state.
The bindings are revoked independently. Proxy method arguments are first restored to the original Python objects;
results are re-exported through the called method's binding, so calls across bindings do not merge revocation scopes.

## Bidirectional shared containers

A Python list appears in JS as a Proxy targeting a real array:

```javascript
left.history.push(7);
left.history[0] = 8;
console.log(left.history.length, left.history.at(-1));
console.log(Array.isArray(left.history)); // true
console.log(left.history.map(x => x * 2));
console.log(JSON.stringify(left.history));
```

The proxy uses the native Array methods provided by the current JSC, including iteration, spread, map/filter/reduce, sorting, and splice.
In-place methods write back to the original Python list; map, slice, and spread still create shallow copies according to JS rules.
Every access synchronously crosses the bridge; native-array performance is not guaranteed.

Python lists remain dense. Assigning beyond the end or increasing length fills positions with Python's `undefined` sentinel.
`delete items[i]` writes undefined without changing length; use `splice(i, 1)` to remove and shift.
These positions count as present for `in`, `Object.keys()`, and map, and serialize as null in JSON.
Use `.at(-1)` for a negative index; `items[-1]` is not Python negative indexing.
List proxies reject extra string/Symbol property writes, descriptor/prototype changes, and freezing.

A Python dict appears as a null-prototype object with properties corresponding to its data keys:

```javascript
options.keys = 42;                    // A string data key, not a Python method.
Object.assign(options, {enabled: true});
delete options.obsolete;
console.log(Object.keys(options));
console.log(JSON.stringify(options));
```

Ordinary property access, in, spread, Object.keys/values/entries, and JSON cover string keys only, including underscore-prefixed keys.
Missing keys return undefined. Integer-index string keys enumerate in numeric order; other string keys follow insertion order.
Before invoking the Proxy, JS converts `options[1]` to `options["1"]`: both access a Python string key, never the integer key 1.
Use the advanced Python interface below for non-string keys; they are not automatically converted to strings.

### Frequent reads

Every live-proxy read crosses the JS/Python boundary, including indices, fields, and length.
Reading a small part of a large container avoids copying the entire graph.
For repeated traversal or computation, copy the needed subtree with `Python.to_value` before the loop and use native JS containers:

```javascript
const history = Python.to_value(left.history);
const total = history.reduce((sum, value) => sum + value, 0);
```

Copying cost depends on data size; whether it pays off also depends on subsequent access count.
A snapshot is independent: later Python changes do not reach it, and editing it does not write back to Python.
Live proxies always read current values. Reusing nested proxy identities does not cache data, lengths, or key sets.
See [Development](development.md#container-read-benchmarks) for the benchmark script and measurement method.

## JS container views in Python

```python
items = view.evaluate("globalThis.items = [1, 2]")  # JSArray
items.append(3)
assert view.evaluate("items.length") == 3
view.evaluate("items[0] = 9")
assert items[0] == 9

options = view.evaluate("globalThis.options = {enabled: false}")  # JSObject
options["enabled"] = True
assert view.evaluate("options.enabled") is True
```

`JSArray` implements MutableSequence, including negative indices, slices, insertion/deletion, append/extend, and sorting.
`JSObject` implements MutableMapping over a JS object's own enumerable string properties, with update, get, pop, and related methods.
They are not built-in list/dict. Native JS sparse arrays keep holes, which read as undefined in Python;
deleting sequence elements from Python shifts later elements. JSObject rejects non-string keys with TypeError and missing keys with KeyError.
Reading invokes JS getters; assignment/deletion follow JS setters, read-only properties, and configurability rules.

Function arguments, return values, attributes, and synchronous/asynchronous evaluation all use shared semantics.
Nested containers are wrapped on demand, supporting cycles, aliases, and mixed references across both sides.
Returning a Python proxy restores the original Python object; returning a JS container restores the original JS object.
For example, when a Python echo returns its JS array argument, `echo(items) === items` is true in JS.
Within one document, a still-live view of the same JS container also preserves Python `is` identity.

Views retain JS handles independently; closing a temporary JSValue does not affect them.
They support close, closed, and with. Explicit closing affects Python aliases holding that same view.
Operations raise PageGone after document invalidation or View/Runtime shutdown.
Passing views between documents raises CrossContext; explicitly copy when independent data is needed.
JS container views do not belong to the PythonBinding through which they were passed,
but Python proxies stored inside them still follow their binding's revocation scope.

## Advanced Python operations

Ordinary JS container operations need no Python namespace. For Python key types, slices, tuples, or keyword arguments,
use the read-only Python namespace installed in every document. The global name Python remains reserved by the bridge.

| JS interface | Behavior |
| --- | --- |
| `Python.getattr(obj, name)` | Reads exposed Python attributes, respecting binding allowlists |
| `Python.getitem/setitem/delitem` | Python indexing, mapping keys, and insertion/deletion; preserves key types |
| `Python.len(obj)` | Python len, including non-string dict keys |
| `Python.contains(obj, value)` | Python membership; checks keys for dict |
| `Python.slice(stop)` / `slice(start, stop, step)` | Creates a Python slice; null represents None |
| `Python.iter(obj)` | JS adapter for a Python iterator, supporting for...of |
| `Python.call(fn, args, kwargs)` | Python call with keyword arguments and awaitables |
| `Python.to_value(obj)` | Explicit recursive copy of basic containers to independent JS Array/Object |

```javascript
Python.setitem(options, 1, "integer key");
console.log(Python.getitem(options, 1));
Python.call(Python.getattr(left.history, 'sort'), [], {reverse: true});
```

Python methods no longer occupy list/dict JS property space; access them through Python.getattr.
Tuples and other Python objects keep the existing proxy rules. Python exceptions retain their type/message when converted to JS Error;
when called through view.evaluate, they appear as JavaScriptError. Awaitables become Promises.
Classes, modules, and binary buffers are not automatically proxied.

## Lifecycle and revocation

`PythonBinding.close()` is idempotent and supports context management. `view.unbind(name)` removes a named binding;
a missing name is a no-op. Successfully rebinding the same name revokes the old binding; failure preserves it.
Closing removes a global name only if it still points to that binding, preserving replacements written by the page.

```python
with view.bind_object("temporary", Counter(0)) as binding:
    view.evaluate("temporary.increment()")
assert binding.closed
```

View retains bindings; dropping a PythonBinding handle does not unbind automatically.
`bind_function()` uses the same binding mechanism and preserves callable identity, restoring the original object when passed back to Python.
Each binding strongly retains exported objects, containers, and methods until explicit unbinding or document invalidation;
prompt release by JS GC is not guaranteed.

After unbinding, all saved proxies, methods, and iterators from that binding immediately become invalid, including nested objects retained by JS.
Reads, writes, calls, enumeration, and membership tests then fail.
Main-frame navigation or View/Runtime closing revokes all relevant bindings and sets existing PythonBinding.closed to true.
Function/property callbacks may unbind themselves, navigate, or close View; document and binding validity are checked before returning.

Thread, input, and Renderer reentry restrictions follow Runtime's rules.
Python references are released through a deferred queue; JSC garbage-collection/finalizer threads do not acquire the GIL.
Proxies do not strongly retain View. `PythonBinding.closed` may be queried from other threads;
operations and explicit closing still require Python's main thread.

## Explicit copying and 0.6.0 migration

Version 0.6.0 changes default conversion of all mutable containers to reference semantics.
Code that relied on ordinary JS containers becoming Python list/dict automatically should specify copy=True
when exporting data, encoding JSON, or retaining data outside the document:

```python
snapshot = view.evaluate("({items: [1, 2]})", copy=True)
snapshot = await view.evaluate_async("Promise.resolve({items: [1, 2]})", copy=True)
snapshot = await page.evaluate("getData()", copy=True)
snapshot = live.to_python(copy=True)  # Supported by JSValue, JSArray, and JSObject.
```

copy=True recursively creates independent Python list/dict; Python dicts are copied as their JS-visible string-key projection.
Shared conversion supports cycles; explicit deep copying rejects cycles or depth beyond 64 with TraversalLimit.
list(live), dict(live), and JS spread only create shallow copies; nested containers remain shared.
JS can call JSON.stringify(live) directly, following JSON rules for undefined, cycles, and toJSON.
For independent basic JS data, Python.to_value remains available; Python dict inputs must have only string keys.

Migrate list.append → list.push, Python.len(list) → list.length,
Python.getitem(list, -1) → list.at(-1), and reading a field after Python.to_value(dict) → direct dict.field access.
Do not rely on Python's reverse argument for items.sort; native JS sort accepts a comparator.
Python sorting remains available through the advanced interface.

Run the examples:

```sh
python examples/objects.py
python examples/tkinter_view.py
python examples/tkinter_view.py --smoke
```
