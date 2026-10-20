#pragma once
#include "async.hpp"
#include <string_view>
namespace binding::objects {
inline py::object policy(const std::shared_ptr<Document> &doc) { return doc->policy->object(); }
inline std::optional<py::object> container_read(Bridge &bridge, py::handle value,
                                              std::string_view operation,
                                              std::span<const JSValueRef> args) {
    if (PyList_CheckExact(value.ptr())) {
        auto length = PyList_GET_SIZE(value.ptr());
        if (operation == "item_length") return py::int_(length);
        if (operation != "item_get" && operation != "item_has") return std::nullopt;
        auto number = bridge.readNumber(args[1]);
        if (!std::isfinite(number) || number < 0 || number >= 4294967295.0 || std::trunc(number) != number)
            throw py::type_error("Invalid Python list property index");
        auto index = static_cast<uint32_t>(number);
        bool present = static_cast<uint64_t>(index) < static_cast<uint64_t>(length);
        if (operation == "item_has") return py::bool_(present);
        return py::reinterpret_borrow<py::object>(present ? PyList_GET_ITEM(value.ptr(), index) : undefined);
    }
    if (PyDict_CheckExact(value.ptr()) && (operation == "item_get" || operation == "item_has")) {
        auto key = py::str(bridge.readString(args[1]));
        if (operation == "item_has") {
            int present = PyDict_Contains(value.ptr(), key.ptr());
            if (present < 0) throw py::error_already_set();
            return py::bool_(present);
        }
        auto item = PyDict_GetItemWithError(value.ptr(), key.ptr());
        if (!item && PyErr_Occurred()) throw py::error_already_set();
        return py::reinterpret_borrow<py::object>(item ? item : undefined);
    }
    return std::nullopt;
}
inline bool exact_scalar(py::handle value) {
    return value.ptr() == undefined || value.is_none() || PyBool_Check(value.ptr()) ||
        PyLong_CheckExact(value.ptr()) || PyFloat_CheckExact(value.ptr()) ||
        PyUnicode_CheckExact(value.ptr());
}
inline bool synchronous_container_result(py::handle value) {
    return exact_scalar(value) || PyList_CheckExact(value.ptr()) ||
        PyDict_CheckExact(value.ptr()) || PyTuple_CheckExact(value.ptr());
}
inline JSValueRef node_call(const std::weak_ptr<Node> &weak, std::span<const JSValueRef> args) {
    py::gil_scoped_acquire gil;
    auto node = weak.lock();
    auto scope = node ? node->session.lock() : nullptr;
    if (!scope) throw Error(Code::PageGone, "Python binding has been revoked");
    scope->check();
    auto doc = scope->document.lock(); auto bridge = doc->bridge.lock();
    try {
        auto ctx = bridge->context();
        std::string decoded;
        std::string_view operation;
        if (JSValueIsNumber(ctx, args[0])) {
            // Private read codes shared with factory.hpp; writes keep their names.
            auto code = JSValueToNumber(ctx, args[0], nullptr);
            if (code == 1) operation = "item_get";
            else if (code == 2) operation = "item_has";
            else if (code == 3) operation = "item_length";
            else throw py::value_error("Unknown Python container read operation");
        } else {
            decoded = bridge->readString(args[0]);
            operation = decoded;
        }
        auto object = node->object->object();
        auto allowed = node->members ? node->members->object() : py::none();
        py::object result;
        if (operation == "guard") return bridge->makeUndefined();
        if (operation.starts_with("item_")) {
            if (auto read = container_read(*bridge, object, operation, args)) result = std::move(*read);
            else {
                auto positional = py::list();
                ulbind17::jsc::Traversal walk;
                for (std::size_t i = 1; i < args.size(); ++i) positional.append(from_js(*bridge, args[i], walk));
                result = policy(doc).attr("container")(object, operation, positional);
                if (scope->closed || !bridge->active()) return nullptr;
                if (operation == "item_keys") return copy_to_js(*bridge, result, walk)->value();
            }
        } else if (operation == "has" || operation == "keys") {
            auto names = policy(doc).attr("members")(object, allowed);
            if (operation == "has") {
                ulbind17::jsc::Traversal walk;
                auto key = from_js(*bridge, args[1], walk);
                result = py::bool_(PySequence_Contains(names.ptr(), key.ptr()) == 1);
            } else result = names;
            ulbind17::jsc::Traversal walk;
            return copy_to_js(*bridge, result, walk)->value();
        } else if (operation == "call") {
            auto positional = arguments_from_js(*bridge, args[1]);
            result = object(*py::tuple(positional));
        } else {
            ulbind17::jsc::Traversal walk;
            auto name = from_js(*bridge, args[1], walk);
            if (operation == "get") result = policy(doc).attr("member")(object, name, allowed);
            else if (operation == "set") {
                auto item = from_js(*bridge, args[2], walk);
                policy(doc).attr("set_member")(object, name, item, allowed);
                result = py::none();
            } else throw py::value_error("Unknown Python proxy operation");
        }
        if (scope->closed || !bridge->active()) return nullptr;
        // Exact scalars have no Python finalizers that could reenter JS while
        // unwinding the callback. Subclasses keep the rooted conversion below.
        if (exact_scalar(result)) return *scalar_to_js(*bridge, result);
        if (auto cached = scope->cached_container(result)) return cached;
        if (!synchronous_container_result(result) &&
            py::module_::import("inspect").attr("isawaitable")(result).cast<bool>())
            return async_result(scope, *bridge, result)->value();
        return scope->convert(*bridge, result)->value();
    } catch (py::error_already_set &error) { throw Error(Code::HostException, error.what()); }
    catch (const py::type_error &error) { throw Error(Code::HostException, std::string("TypeError: ") + error.what()); }
}
inline std::unique_ptr<Bridge::Handle> Session::convert(Bridge &b, py::handle value, py::handle members) {
    check();
    if (auto cached = cached_container(value)) return b.retain(cached);
    bool exact_container = PyList_CheckExact(value.ptr()) || PyDict_CheckExact(value.ptr());
    if (py::isinstance<HostValue>(value)) return HostValue::convert(b, value);
    if (value.ptr() == undefined || value.is_none() || py::isinstance<py::bool_>(value) ||
        py::isinstance<py::int_>(value) || py::isinstance<py::float_>(value) || py::isinstance<py::str>(value)) {
        ulbind17::jsc::Traversal walk; return copy_to_js(b, value, walk);
    }
    auto doc = document.lock();
    auto unwrapped = policy(doc).attr("unwrap")(value);
    if (py::isinstance<HostValue>(unwrapped)) return HostValue::convert(b, unwrapped);
    policy(doc).attr("validate")(value);
    auto key = py::str(policy(doc).attr("identity")(value)).cast<std::string>();
    auto found = nodes.find(key);
    if (found != nodes.end()) return b.retain(found->second->proxy->value());
    auto node = std::make_shared<Node>();
    node->object = reference(value); node->session = shared_from_this();
    if (!members.is_none()) node->members = reference(members);
    auto native = b.retain(b.makeFunction([weak = std::weak_ptr<Node>(node)](JSContextRef, JSObjectRef, std::span<const JSValueRef> args) {
        return node_call(weak, args);
    }));
    auto token = b.retain(b.makeObject(std::weak_ptr<Node>(node), Bridge::ObjectHooks{}));
    auto kind = py::isinstance<py::list>(value) ? "list" : py::isinstance<py::dict>(value) ? "dict" : "object";
    ulbind17::jsc::Traversal walk;
    auto shape = copy_to_js(b, py::str(kind), walk);
    const JSValueRef args[] = {native->value(), b.makeBoolean(PyCallable_Check(value.ptr())), token->value(), shape->value()};
    node->proxy = doc->invoke(b, "proxy", args);
    nodes.emplace(key, node);
    if (exact_container) exact_containers[value.ptr()] = node;
    return b.retain(node->proxy->value());
}
} // namespace binding::objects
