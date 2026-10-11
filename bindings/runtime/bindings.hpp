#pragma once
#include "views.hpp"
namespace binding {
inline void register_runtime(py::module_ &module) {
  py::class_<HostRuntime, std::shared_ptr<HostRuntime>>(module, "_Runtime")
      .def_static("create", &HostRuntime::create)
      .def("create_view", &HostRuntime::create_view)
      .def("update", [](HostRuntime &host) {
          host.check();
          { py::gil_scoped_release release; host.runtime->Update(); }
          host.flush_errors();
          std::erase_if(host.views, [](auto &view) { return view->closed; });
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
