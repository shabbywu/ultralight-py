#pragma once
#include "keyboard.hpp"
#include "key_codes.hpp"
namespace binding {
inline void register_keyboard_input(py::module_ &module) {
    auto view = py::reinterpret_borrow<py::class_<HostView, std::shared_ptr<HostView>>>(module.attr("_View"));
    view.def("fire_key_event", &key_event);
    register_key_codes(module);
}
} // namespace binding
