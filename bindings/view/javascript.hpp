#pragma once
#include "../javascript/value.hpp"
namespace binding {
// View evaluation and Python function binding connect View with JSValue.
inline std::shared_ptr<HostValue> HostView::evaluate(std::string source) {
    check(); auto self = shared_from_this();
    return view->WithBridge([&](Bridge &bridge) {
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
inline void HostView::bind_function(std::string name, py::object function) {
    check(); auto callback = reference(function);
    auto weak = weak_from_this();
    view->WithBridge([&](Bridge &bridge) {
        auto fn = bridge.retain(bridge.makeFunction([callback, weak](JSContextRef, JSObjectRef, std::span<const JSValueRef> args) {
            py::gil_scoped_acquire gil;
            auto owner = weak.lock();
            if (!owner || owner->closed) throw Error(Code::PageGone, "Python callback belongs to an expired View");
            return owner->view->WithBridge([&](Bridge &bridge) -> JSValueRef {
                try {
                    py::tuple converted(args.size());
                    for (std::size_t i = 0; i < args.size(); ++i) {
                        ulbind17::jsc::Traversal walk; converted[i] = from_js(bridge, args[i], walk);
                    }
                    auto result = callback->object()(*converted);
                    if (owner->closed || !bridge.active()) return nullptr;
                    // Handle destruction posts unprotect to a later Update, keeping
                    // the result rooted until JSC consumes this callback's return.
                    auto value = HostValue::convert(bridge, result);
                    return value->value();
                } catch (py::error_already_set &error) { throw Error(Code::HostException, error.what()); }
            });
        }));
        auto text = unicode(name);
        ulbind17::jsc::String key{std::span<const char16_t>(text)};
        without_gil([&] { bridge.bind(key, fn->value()); });
    });
}
} // namespace binding
