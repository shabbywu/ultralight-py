#pragma once
#include "pointer.hpp"
namespace binding {
inline void register_input(py::module_ &module) {
    // Extend the registered View type without framework-specific event objects.
    auto view = py::reinterpret_borrow<py::class_<HostView, std::shared_ptr<HostView>>>(module.attr("_View"));
    view.def("_check_input", [](HostView &host) { host.check(); })
        .def("fire_mouse_event", &mouse_event)
        .def("fire_scroll_event", &scroll_event)
        .def("focus", [](HostView &host) { with_input(host, [](auto &view) { view.Focus(); }); })
        .def("unfocus", [](HostView &host) { with_input(host, [](auto &view) { view.Unfocus(); }); })
        .def_property_readonly("has_focus", [](HostView &host) { return with_input(host, [](auto &view) { return view.HasFocus(); }); })
        .def_property_readonly("has_input_focus", [](HostView &host) { return with_input(host, [](auto &view) { return view.HasInputFocus(); }); });
}
} // namespace binding
