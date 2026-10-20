#pragma once
#include "../common.hpp"
#include <ulbind17/jsc/Traversal.hpp>
#include <cmath>
#include <optional>
namespace binding {
struct Undefined {};
inline PyObject *undefined = nullptr; // borrowed from the module, only used with the GIL

// Python's length-aware Unicode representation preserves embedded NULs. Use
// Bridge's UTF-16 entrypoint instead of the SDK's UTF-8 String conversion.
inline std::u16string unicode(py::handle value) {
    std::u16string result;
    auto length = PyUnicode_GetLength(value.ptr());
    if (length < 0) throw py::error_already_set();
    for (Py_ssize_t i = 0; i < length; ++i) {
        auto ch = PyUnicode_ReadChar(value.ptr(), i);
        if (ch <= 0xffff) result.push_back(static_cast<char16_t>(ch));
        else {
            ch -= 0x10000;
            result.push_back(static_cast<char16_t>(0xd800 + (ch >> 10)));
            result.push_back(static_cast<char16_t>(0xdc00 + (ch & 1023)));
        }
    }
    return result;
}
inline std::u16string unicode(std::string_view value) { return unicode(py::str(value)); }
inline std::unique_ptr<Bridge::Handle> get_property(Bridge &bridge, JSValueRef target, std::string_view name) {
    auto ctx = bridge.context();
    auto target_root = bridge.retain(target);
    if (!JSValueIsObject(ctx, target)) throw Error(Code::TypeMismatch, "Expected a JavaScript object");
    auto text = unicode(name);
    ulbind17::jsc::String key{std::span<const char16_t>(text)};
    ulbind17::jsc::ContextScope context(ctx);
    JSValueRef exception = nullptr;
    JSValueRef result;
    {
        py::gil_scoped_release release;
        result = JSObjectGetProperty(ctx, JSValueToObject(ctx, target, nullptr), key, &exception);
    }
    if (!bridge.active()) throw Error(Code::PageGone, "Document expired during property access");
    ulbind17::jsc::check(ctx, exception);
    return bridge.retain(result);
}
inline void set_property(Bridge &bridge, JSValueRef target, std::string_view name, JSValueRef value) {
    auto ctx = bridge.context();
    auto target_root = bridge.retain(target), value_root = bridge.retain(value);
    if (!JSValueIsObject(ctx, target)) throw Error(Code::TypeMismatch, "Expected a JavaScript object");
    auto text = unicode(name);
    ulbind17::jsc::String key{std::span<const char16_t>(text)};
    ulbind17::jsc::ContextScope context(ctx);
    JSValueRef exception = nullptr;
    {
        py::gil_scoped_release release;
        JSObjectSetProperty(ctx, JSValueToObject(ctx, target, nullptr), key, value, kJSPropertyAttributeNone, &exception);
    }
    if (!bridge.active()) throw Error(Code::PageGone, "Document expired during property assignment");
    ulbind17::jsc::check(ctx, exception);
}

std::optional<py::object> proxy_from_js(Bridge &, JSValueRef);
std::unique_ptr<Bridge::Handle> to_js(Bridge &, py::handle);
py::object container_from_js(Bridge &, JSValueRef, bool);
bool is_array(Bridge &, JSValueRef);
std::optional<py::object> copied_js_container(Bridge &, py::handle, ulbind17::jsc::Traversal &);
std::unique_ptr<Bridge::Handle> copy_to_js(Bridge &, py::handle, ulbind17::jsc::Traversal &);

inline py::object from_js(Bridge &bridge, JSValueRef value, ulbind17::jsc::Traversal &walk, bool copy = false) {
    auto ctx = bridge.context();
    auto root = bridge.retain(value);
    if (JSValueIsUndefined(ctx, value)) return py::reinterpret_borrow<py::object>(undefined);
    if (JSValueIsNull(ctx, value)) return py::none();
    if (JSValueIsBoolean(ctx, value)) return py::bool_(bridge.readBoolean(value));
    if (JSValueIsNumber(ctx, value)) {
        auto number = bridge.readNumber(value);
        if (std::isfinite(number) && std::abs(number) <= 9007199254740991.0 && std::trunc(number) == number && !(number == 0 && std::signbit(number)))
            return py::int_(static_cast<long long>(number));
        return py::float_(number);
    }
    if (JSValueIsString(ctx, value)) return py::str(bridge.readString(value));
    if (!JSValueIsObject(ctx, value)) throw py::type_error("JavaScript value requires a JSValue handle");
    if (auto proxy = proxy_from_js(bridge, value)) {
        if (!copy) return *proxy;
        if (py::isinstance<py::tuple>(*proxy)) {
            auto snapshot = copy_to_js(bridge, *proxy, walk);
            return from_js(bridge, snapshot->value(), walk, true);
        }
        if (!py::isinstance<py::list>(*proxy) && !py::isinstance<py::dict>(*proxy))
            throw py::type_error("Only basic containers can be copied");
    }
    auto object = JSValueToObject(ctx, value, nullptr);
    if (JSObjectIsFunction(ctx, object) || bridge.isPromise(value))
        throw py::type_error("Functions and Promises require a JSValue handle");
    if (is_array(bridge, value)) {
        if (!copy) return container_from_js(bridge, value, true);
        auto guard = walk.enter(object);
        py::list result;
        auto length_value = get_property(bridge, value, "length");
        auto number = bridge.readNumber(length_value->value());
        if (!std::isfinite(number) || number < 0 || number > 4294967295.0 || std::trunc(number) != number)
            throw Error(Code::TypeMismatch, "Invalid JavaScript array length");
        auto length = static_cast<std::size_t>(number);
        for (std::size_t i = 0; i < length; ++i) {
            auto property = get_property(bridge, value, std::to_string(i));
            result.append(from_js(bridge, property->value(), walk, true));
        }
        return std::move(result);
    }
    // Only plain objects (including Object.create(null)) are value containers.
    auto prototype = without_gil([&] { return bridge.retain(JSObjectGetPrototype(ctx, object)); });
    if (!bridge.active()) throw Error(Code::PageGone, "Document expired during prototype access");
    if (!JSValueIsNull(ctx, prototype->value())) {
        auto global = JSContextGetGlobalObject(ctx);
        auto constructor = get_property(bridge, global, "Object");
        auto expected = get_property(bridge, constructor->value(), "prototype");
        if (!JSValueIsStrictEqual(ctx, prototype->value(), expected->value()))
            throw py::type_error("Non-plain JavaScript objects require a JSValue handle");
    }
    if (!copy) return container_from_js(bridge, value, false);
    auto guard = walk.enter(object);
    py::dict result;
    auto keys = without_gil([&] { return bridge.keys(value); });
    for (const auto &key : keys) {
        auto property = get_property(bridge, value, key);
        result[py::str(key)] = from_js(bridge, property->value(), walk, true);
    }
    return std::move(result);
}
// The argument envelope belongs to the bridge; only its elements are user values.
inline py::list arguments_from_js(Bridge &bridge, JSValueRef args) {
    py::list result;
    ulbind17::jsc::Traversal walk;
    auto length = without_gil([&] { return bridge.length(args); });
    for (std::size_t i = 0; i < length; ++i) {
        auto value = get_property(bridge, args, std::to_string(i));
        result.append(from_js(bridge, value->value(), walk));
    }
    return result;
}
// Unretained values are for immediate callback returns. Other callers must root
// them before executing anything that could reenter JavaScript or trigger GC.
inline std::optional<JSValueRef> scalar_to_js(Bridge &bridge, py::handle value) {
    if (value.ptr() == undefined) return bridge.makeUndefined();
    if (value.is_none()) return bridge.makeNull();
    if (py::isinstance<py::bool_>(value)) return bridge.makeBoolean(value.cast<bool>());
    if (py::isinstance<py::int_>(value)) {
        constexpr long long limit = 9007199254740991LL;
        int overflow = 0;
        auto integer = PyLong_AsLongLongAndOverflow(value.ptr(), &overflow);
        if (PyErr_Occurred()) throw py::error_already_set();
        if (overflow || integer < -limit || integer > limit) {
            PyErr_SetString(PyExc_OverflowError, "Python int exceeds the JavaScript safe integer range");
            throw py::error_already_set();
        }
        return bridge.makeNumber(static_cast<double>(integer));
    }
    if (py::isinstance<py::float_>(value)) return bridge.makeNumber(value.cast<double>());
    if (py::isinstance<py::str>(value)) {
        auto text = unicode(value);
        ulbind17::jsc::String string{std::span<const char16_t>(text)};
        return JSValueMakeString(bridge.context(), string);
    }
    return std::nullopt;
}
inline std::unique_ptr<Bridge::Handle> copy_to_js(Bridge &bridge, py::handle value,
                                          ulbind17::jsc::Traversal &walk) {
    if (auto scalar = scalar_to_js(bridge, value)) return bridge.retain(*scalar);
    if (py::isinstance<py::list>(value) || py::isinstance<py::tuple>(value)) {
        auto guard = walk.enter(value.ptr());
        auto array = bridge.retain(bridge.makeArray());
        uint32_t index = 0;
        for (auto item : py::reinterpret_borrow<py::iterable>(value)) {
            auto converted = copy_to_js(bridge, item, walk);
            set_property(bridge, array->value(), std::to_string(index++), converted->value());
        }
        return array;
    }
    if (py::isinstance<py::dict>(value)) {
        auto guard = walk.enter(value.ptr());
        auto object = bridge.retain(bridge.makePlainObject());
        JSObjectSetPrototype(bridge.context(), JSValueToObject(bridge.context(), object->value(), nullptr),
                             bridge.makeNull());
        for (auto item : py::reinterpret_borrow<py::dict>(value)) {
            if (!py::isinstance<py::str>(item.first)) throw py::type_error("Dictionary keys must be strings");
            auto converted = copy_to_js(bridge, item.second, walk);
            set_property(bridge, object->value(), item.first.cast<std::string>(), converted->value());
        }
        return object;
    }
    if (auto copied = copied_js_container(bridge, value, walk)) return copy_to_js(bridge, *copied, walk);
    throw py::type_error("Unsupported Python value; use basic values or a JSValue handle");
}
} // namespace binding
