#pragma once
#include "operators.hpp"
#include "factory.hpp"
namespace binding::objects {
inline std::shared_ptr<Document> document(Bridge &b, std::shared_ptr<HostView> owner) {
    if (auto found = documents.find(&b); found != documents.end()) {
        if (auto value = found->second.lock()) {
            if (owner) value->view = owner;
            return value;
        }
        documents.erase(found);
    }
    auto doc = std::make_shared<Document>(); doc->bridge = b.shared_from_this(); doc->registry_key = &b;
    doc->view = owner;
    doc->containers = reference(py::module_::import("weakref").attr("WeakValueDictionary")());
    doc->policy = reference(py::module_::import("ultralight_py._objects"));
    doc->implicit = doc->session();
    doc->factory = without_gil([&] {
        ulbind17::jsc::String source(factory_source); return b.retain(b.evaluate(source));
    });
    auto helper = b.retain(b.makeFunction([weak = std::weak_ptr<Document>(doc)](JSContextRef, JSObjectRef, std::span<const JSValueRef> args) { return helper_call(weak, args); }));
    const JSValueRef args[] = {helper->value()};
    doc->invoke(b, "install", args);
    // Bridge invalidation clears this rooted closure before dropping the JS
    // context. No Python state is owned by a JSC finalizer or proxy payload.
    auto lifetime = b.makeFunction([doc](JSContextRef ctx, JSObjectRef, std::span<const JSValueRef>) { return JSValueMakeUndefined(ctx); });
    b.protect(lifetime);
    documents[&b] = doc;
    return doc;
}
} // namespace binding::objects
namespace binding {
inline bool is_array(Bridge &b, JSValueRef value) {
    // JSC's C API does not recognize array proxies in this SDK. Use IsArray.
    const JSValueRef args[] = {value};
    auto result = objects::document(b)->invoke(b, "array", args);
    return b.readBoolean(result->value());
}
inline py::object container_from_js(Bridge &b, JSValueRef value, bool array) {
    auto doc = objects::document(b);
    const JSValueRef args[] = {value};
    auto token = doc->invoke(b, "identify", args);
    auto key = py::int_(static_cast<uint64_t>(b.readNumber(token->value())));
    auto cache = doc->containers->object();
    auto existing = cache.attr("get")(key);
    if (!existing.is_none() && !existing.attr("closed").cast<bool>()) return existing;
    auto owner = doc->view.lock();
    if (!owner) throw Error(Code::PageGone, "JavaScript container View expired");
    auto cls = py::module_::import("ultralight_py.api.values").attr(array ? "JSArray" : "JSObject");
    auto result = cls(py::cast(HostValue::make(owner, b.retain(value))));
    cache[key] = result;
    return result;
}
inline py::object container_operation(Bridge &b, JSValueRef value, const std::string &operation, py::args args) {
    ulbind17::jsc::Traversal walk;
    auto name = copy_to_js(b, py::str(operation), walk);
    std::vector<std::unique_ptr<Bridge::Handle>> roots;
    std::vector<JSValueRef> values{value, name->value()};
    for (auto arg : args) {
        roots.push_back(HostValue::convert(b, arg));
        values.push_back(roots.back()->value());
    }
    auto result = objects::document(b)->invoke(b, "container", values);
    return from_js(b, result->value(), walk);
}
inline std::optional<py::object> copied_js_container(Bridge &b, py::handle value, ulbind17::jsc::Traversal &walk) {
    auto source = objects::document(b)->policy->object().attr("unwrap")(value);
    if (!py::isinstance<HostValue>(source)) return {};
    auto original = HostValue::convert(b, source);
    return from_js(b, original->value(), walk, true);
}
inline std::optional<py::object> proxy_from_js(Bridge &b, JSValueRef value) {
    auto found = objects::documents.find(&b);
    if (found == objects::documents.end()) return {};
    auto doc = found->second.lock();
    if (!doc) return {};
    auto node = doc->find(value);
    if (!node) return {};
    return node->object->object();
}
inline std::unique_ptr<Bridge::Handle> to_js(Bridge &b, py::handle value) {
    return objects::document(b)->implicit->convert(b, value);
}
} // namespace binding
