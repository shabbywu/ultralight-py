#pragma once
#include "application.hpp"
namespace binding {
inline void register_appcore(py::module_ &module) {
    py::class_<HostWindow, std::shared_ptr<HostWindow>>(module, "_Window")
        .def("close", &HostWindow::close).def("check", [](HostWindow &window) { window.check(); })
        .def("set_callback", &HostWindow::set_callback)
        .def_readonly("closed", &HostWindow::closed).def_readonly("view", &HostWindow::view)
        .def_property_readonly("width", [](HostWindow &w) { w.check(); return w.window->native()->width(); })
        .def_property_readonly("height", [](HostWindow &w) { w.check(); return w.window->native()->height(); })
        .def_property_readonly("device_width", [](HostWindow &w) { w.check(); return w.window->native()->device_width(); })
        .def_property_readonly("device_height", [](HostWindow &w) { w.check(); return w.window->native()->device_height(); })
        .def_property_readonly("device_scale", [](HostWindow &w) { w.check(); return w.window->native()->scale(); })
        .def("set_title", [](HostWindow &w, std::string title) { w.check(); w.window->native()->SetTitle(title.c_str()); });
    py::class_<HostApplication, std::shared_ptr<HostApplication>>(module, "_Application")
        .def_static("create", &HostApplication::create)
        .def_readonly("runtime", &HostApplication::runtime)
        .def("create_window", &HostApplication::create_window)
        .def("run_once", &HostApplication::run_once).def("close", &HostApplication::close)
        .def("check", [](HostApplication &app) { app.check(); });
}
} // namespace binding
