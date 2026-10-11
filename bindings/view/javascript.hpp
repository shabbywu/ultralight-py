#pragma once
#include "../javascript/objects/operators.hpp"
namespace binding {
// View evaluation and Python function binding connect View with JSValue.
inline std::shared_ptr<HostValue> HostView::evaluate(std::string source) {
    check(); auto self = shared_from_this();
    return view->WithBridge([&](Bridge &bridge) {
        (void)objects::document(bridge);
        auto text = unicode(source);
        ulbind17::jsc::String script{std::span<const char16_t>(text)};
        std::unique_ptr<Bridge::Handle> result;
        {
            py::gil_scoped_release release;
            auto value = bridge.evaluate(script);
            if (!bridge.active()) throw Error(Code::PageGone, "Document expired during evaluation");
            result = bridge.retain(value);
        }
        return HostValue::make(self, std::move(result));
    });
}
inline std::shared_ptr<objects::Session> HostView::bind_object(std::string name, py::object value, py::object members) {
    check();
    if (name.empty() || name == "Python") throw py::value_error("Binding name must be nonempty and cannot be Python");
    return view->WithBridge([&](Bridge &bridge) {
        auto doc = objects::document(bridge); auto scope = doc->session();
        auto proxy = scope->convert(bridge, value, members);
        ulbind17::jsc::Traversal walk;
        auto key = copy_to_js(bridge, py::str(name), walk);
        const JSValueRef args[] = {key->value(), proxy->value()};
        doc->invoke(bridge, "bind", args);
        if (auto old = doc->bindings.find(name); old != doc->bindings.end()) old->second->invalidate();
        scope->name = name; scope->root = proxy->value();
        doc->bindings[name] = scope;
        return scope;
    });
}
inline std::shared_ptr<objects::Session> HostView::bind_function(std::string name, py::object callback) {
    return bind_object(std::move(name), std::move(callback), py::none());
}
inline void HostView::unbind(std::string name) {
    check();
    view->WithBridge([&](Bridge &bridge) {
        auto found = objects::documents.find(&bridge);
        auto doc = found == objects::documents.end() ? nullptr : found->second.lock();
        if (!doc) return;
        auto binding = doc->bindings.find(name);
        if (binding != doc->bindings.end()) { auto scope = binding->second; scope->close(); }
    });
}
} // namespace binding
