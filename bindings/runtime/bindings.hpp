#pragma once
#include "views.hpp"
namespace binding {
inline void register_runtime(py::module_ &module) {
  py::class_<HostSession, std::shared_ptr<HostSession>>(module, "_Session")
      .def("close", &HostSession::close)
      .def("check", &HostSession::check)
      .def_readonly("closed", &HostSession::closed)
      .def_readonly("disk_path", &HostSession::disk_path);
  py::class_<HostRuntime, std::shared_ptr<HostRuntime>>(module, "_Runtime")
      .def_static("create", &HostRuntime::create)
      .def("create_view", &HostRuntime::create_view, py::arg("width"), py::arg("height"), py::arg("transparent"), py::arg("session") = nullptr)
      .def("create_session", &HostRuntime::create_session)
      .def("check", [](HostRuntime &host) { host.check(); })
      .def("update", [](HostRuntime &host) {
          host.check();
          { py::gil_scoped_release release; host.runtime->Update(); }
          host.flush_errors();
      })
      .def("refresh_display", [](HostRuntime &host, uint32_t display) {
          host.check(); py::gil_scoped_release release; host.runtime->RefreshDisplay(display);
      })
      .def("render", [](HostRuntime &host) {
          host.check(); py::gil_scoped_release release; host.runtime->Render();
      })
      .def("set_error_handler", [](HostRuntime &host, py::object callback) {
          host.check(); host.error_handler = callback.is_none() ? nullptr : reference(callback);
      })
      .def("close", &HostRuntime::close)
      .def_readonly("closed", &HostRuntime::closed);
}
} // namespace binding
