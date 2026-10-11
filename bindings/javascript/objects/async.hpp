#pragma once
#include "state.hpp"
namespace binding::objects {
struct Delivery {
    std::weak_ptr<Session> session;
    std::unique_ptr<Bridge::Handle> resolve, reject;
    Ref cancel;
    bool closed = false;
    void close() { closed = true; resolve.reset(); reject.reset(); cancel.reset(); }
    void invalidate() {
        py::gil_scoped_acquire gil;
        auto callback = cancel;
        close();
        if (callback) callback->object()();
    }
    void settle(py::object value, bool rejected) {
        if (closed) return;
        auto scope = session.lock();
        if (!scope || scope->closed) { invalidate(); return; }
        scope->check();
        auto doc = scope->document.lock(); auto bridge = doc->bridge.lock();
        std::unique_ptr<Bridge::Handle> result;
        try { result = scope->convert(*bridge, value); }
        catch (std::exception &error) {
            rejected = true;
            ulbind17::jsc::Traversal walk;
            result = copy_to_js(*bridge, py::str(error.what()), walk);
        }
        auto fn = rejected ? reject.get() : resolve.get();
        const Bridge::Handle *args[] = {result.get()};
        without_gil([&] { bridge->callRetained(*fn, args); });
    }
};
inline std::unique_ptr<Bridge::Handle> async_result(const std::shared_ptr<Session> &scope, Bridge &b, py::object value) {
    auto delivery = std::make_shared<Delivery>(); delivery->session = scope;
    JSObjectRef resolve = nullptr, reject = nullptr;
    JSValueRef exception = nullptr;
    auto promise = JSObjectMakeDeferredPromise(b.context(), &resolve, &reject, &exception);
    ulbind17::jsc::check(b.context(), exception);
    auto root = b.retain(promise);
    delivery->resolve = b.retain(resolve); delivery->reject = b.retain(reject);
    scope->async_cleanup.push_back([weak = std::weak_ptr<Delivery>(delivery)] {
        if (auto d = weak.lock()) d->invalidate();
    });
    py::module_::import("ultralight_py.integrations.asyncio").attr("_start")(value, py::cast(delivery));
    return root;
}
} // namespace binding::objects
