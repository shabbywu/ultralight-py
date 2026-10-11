#pragma once
#include "../view/view.hpp"
#include "conversion.hpp"
namespace binding {
struct HostValue {
    std::weak_ptr<HostView> view;
    std::unique_ptr<Bridge::Handle> handle;
    bool closed = false;
    std::shared_ptr<HostView> checked() const {
        auto owner = view.lock();
        if (!owner || owner->closed || closed) throw Error(Code::PageGone, "JavaScript handle is closed or its View expired");
        owner->check(); return owner;
    }
    template <typename F> decltype(auto) with(F &&callback) const {
        auto owner = checked();
        return owner->view->WithBridge([&](Bridge &bridge) -> decltype(auto) {
            (void)handle->value(); return callback(bridge);
        });
    }
    static std::shared_ptr<HostValue> make(std::shared_ptr<HostView> owner, std::unique_ptr<Bridge::Handle> handle) {
        auto result = std::make_shared<HostValue>(); result->view = owner; result->handle = std::move(handle); return result;
    }
    std::shared_ptr<HostValue> get(py::object key) {
        auto owner = checked();
        auto name = property_key(key);
        return with([&](Bridge &bridge) { return make(owner, get_property(bridge, handle->value(), name)); });
    }
    static std::string property_key(py::handle key) {
        if (py::isinstance<py::str>(key)) return key.cast<std::string>();
        if (py::isinstance<py::int_>(key) && !py::isinstance<py::bool_>(key)) return py::str(key).cast<std::string>();
        throw py::type_error("Property key must be str or int");
    }
    static std::unique_ptr<Bridge::Handle> convert(Bridge &bridge, py::handle value) {
        if (py::isinstance<HostValue>(value)) {
            auto other = value.cast<std::shared_ptr<HostValue>>(); other->checked();
            // Compare bridge ownership before borrowing a raw document value.
            auto other_owner = other->view.lock();
            bool matches = other_owner->view->WithBridge([&](Bridge &other_bridge) { return &other_bridge == &bridge; });
            if (!matches) throw Error(Code::CrossContext, "JavaScript handle belongs to another document");
            return bridge.retain(other->handle->value());
        }
        return to_js(bridge, value);
    }
    void set(py::object key, py::object value) {
        auto name = property_key(key);
        with([&](Bridge &bridge) { auto converted = convert(bridge, value); set_property(bridge, handle->value(), name, converted->value()); });
    }
    py::object python() {
        return with([&](Bridge &bridge) { ulbind17::jsc::Traversal walk; return from_js(bridge, handle->value(), walk); });
    }
    std::shared_ptr<HostValue> call(py::args args, py::object receiver) {
        auto owner = checked();
        return with([&](Bridge &bridge) {
            std::vector<std::unique_ptr<Bridge::Handle>> roots;
            std::vector<const Bridge::Handle *> values;
            for (auto arg : args) { roots.push_back(convert(bridge, arg)); values.push_back(roots.back().get()); }
            auto this_value = receiver.is_none() ? nullptr : convert(bridge, receiver);
            std::unique_ptr<Bridge::Handle> result;
            { py::gil_scoped_release release; result = bridge.callRetained(*handle, values, this_value.get()); }
            return make(owner, std::move(result));
        });
    }
    void close() {
        if (auto owner = view.lock()) owner->check(false);
        closed = true; handle.reset();
    }
};
} // namespace binding
