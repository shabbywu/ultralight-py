#pragma once
#include "operators.hpp"
#include "factory.hpp"
namespace binding::objects {
inline std::shared_ptr<Document> document(Bridge &b) {
    if (auto found = documents.find(&b); found != documents.end()) {
        if (auto value = found->second.lock()) return value;
        documents.erase(found);
    }
    auto doc = std::make_shared<Document>(); doc->bridge = b.shared_from_this(); doc->registry_key = &b;
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
