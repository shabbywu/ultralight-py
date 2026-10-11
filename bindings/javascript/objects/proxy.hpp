#pragma once
#include "state.hpp"
namespace binding::objects {
inline py::object policy(const std::shared_ptr<Document> &doc) { return doc->policy->object(); }
inline JSValueRef node_call(const std::weak_ptr<Node> &weak, std::span<const JSValueRef> args) {
    py::gil_scoped_acquire gil;
    auto node = weak.lock();
    auto scope = node ? node->session.lock() : nullptr;
    if (!scope) throw Error(Code::PageGone, "Python binding has been revoked");
    scope->check();
    auto doc = scope->document.lock(); auto bridge = doc->bridge.lock();
    auto operation = bridge->readString(args[0]);
    try {
        auto object = node->object->object();
        auto allowed = node->members ? node->members->object() : py::none();
        py::object result;
        if (operation == "guard") return bridge->makeUndefined();
        if (operation == "has" || operation == "keys") {
            auto names = policy(doc).attr("_members")(object, allowed);
            if (operation == "has") {
                ulbind17::jsc::Traversal walk;
                auto key = from_js(*bridge, args[1], walk);
                result = py::bool_(PySequence_Contains(names.ptr(), key.ptr()) == 1);
            } else result = names;
            ulbind17::jsc::Traversal walk;
            return copy_to_js(*bridge, result, walk)->value();
        }
        if (operation == "call") {
            ulbind17::jsc::Traversal walk;
            auto positional = from_js(*bridge, args[1], walk);
            result = object(*py::tuple(positional));
        } else {
            ulbind17::jsc::Traversal walk;
            auto name = from_js(*bridge, args[1], walk);
            if (operation == "get") result = policy(doc).attr("_member")(object, name, allowed);
            else if (operation == "set") {
                auto item = from_js(*bridge, args[2], walk);
                policy(doc).attr("_set")(object, name, item, allowed);
                result = py::none();
            } else throw py::value_error("Unknown Python proxy operation");
        }
        if (scope->closed || !bridge->active()) return nullptr;
        return scope->convert(*bridge, result)->value();
    } catch (py::error_already_set &error) { throw Error(Code::HostException, error.what()); }
    catch (const py::type_error &error) { throw Error(Code::HostException, std::string("TypeError: ") + error.what()); }
}
inline std::unique_ptr<Bridge::Handle> Session::convert(Bridge &b, py::handle value, py::handle members) {
    check();
    if (py::isinstance<HostValue>(value)) return HostValue::convert(b, value);
    if (value.ptr() == undefined || value.is_none() || py::isinstance<py::bool_>(value) ||
        py::isinstance<py::int_>(value) || py::isinstance<py::float_>(value) || py::isinstance<py::str>(value)) {
        ulbind17::jsc::Traversal walk; return copy_to_js(b, value, walk);
    }
    auto doc = document.lock();
    auto unwrapped = policy(doc).attr("_unwrap")(value);
    if (py::isinstance<HostValue>(unwrapped)) return HostValue::convert(b, unwrapped);
    policy(doc).attr("_validate")(value);
    auto key = py::str(policy(doc).attr("_identity")(value)).cast<std::string>();
    auto found = nodes.find(key);
    if (found != nodes.end()) return b.retain(found->second->proxy->value());
    auto node = std::make_shared<Node>();
    node->object = reference(value); node->session = shared_from_this();
    if (!members.is_none()) node->members = reference(members);
    auto native = b.retain(b.makeFunction([weak = std::weak_ptr<Node>(node)](JSContextRef, JSObjectRef, std::span<const JSValueRef> args) {
        return node_call(weak, args);
    }));
    auto token = b.retain(b.makeObject(std::weak_ptr<Node>(node), Bridge::ObjectHooks{}));
    const JSValueRef args[] = {native->value(), b.makeBoolean(PyCallable_Check(value.ptr())), token->value()};
    node->proxy = doc->invoke(b, "proxy", args);
    nodes.emplace(key, node);
    return b.retain(node->proxy->value());
}
} // namespace binding::objects
