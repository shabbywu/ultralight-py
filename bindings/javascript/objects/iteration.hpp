#pragma once
#include "proxy.hpp"
#include <algorithm>
namespace binding::objects {
// The session owns active iterators; JS closures only own deferred Ref holders.
inline JSValueRef make_iterator(const std::shared_ptr<Session> &scope, Bridge &bridge, py::handle value) {
    auto b = &bridge;
    auto raw = PyObject_GetIter(value.ptr());
    if (!raw) throw py::error_already_set();
    auto iterator = py::reinterpret_steal<py::object>(raw);
    if (scope->closed || !b->active()) return nullptr;
    auto holder = std::make_shared<Ref>(reference(iterator));
    scope->cursors.push_back(holder);
    auto next = b->retain(b->makeFunction([holder, weak_scope = std::weak_ptr<Session>(scope)](JSContextRef, JSObjectRef, std::span<const JSValueRef> args) -> JSValueRef {
        py::gil_scoped_acquire gil;
        auto scope = weak_scope.lock();
        if (!scope) throw Error(Code::PageGone, "Python iterator binding expired");
        scope->check(); auto doc = scope->document.lock(); auto b = doc->bridge.lock();
        try {
            bool done = !*holder;
            py::object item = py::none();
            if (!args.empty() && b->readBoolean(args[0])) { holder->reset(); done = true; }
            if (!done) {
                auto iterator = (*holder)->object();
                auto raw = PyIter_Next(iterator.ptr());
                if (!raw && PyErr_Occurred()) throw py::error_already_set();
                if (raw) item = py::reinterpret_steal<py::object>(raw);
                else { done = true; holder->reset(); }
            }
            if (done) std::erase(scope->cursors, holder);
            if (scope->closed || !b->active()) return nullptr;
            auto value = b->retain(b->makePlainObject());
            set_property(*b, value->value(), "done", b->makeBoolean(done));
            auto converted = scope->convert(*b, item);
            set_property(*b, value->value(), "value", converted->value());
            return value->value();
        } catch (py::error_already_set &error) { throw Error(Code::HostException, error.what()); }
        catch (const py::type_error &error) { throw Error(Code::HostException, std::string("TypeError: ") + error.what()); }
    }));
    return next->value();
}
} // namespace binding::objects
