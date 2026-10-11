#pragma once
#include "value.hpp"
namespace binding {
inline void register_javascript(py::module_ &module) {
  py::class_<HostValue, std::shared_ptr<HostValue>>(module, "_JSValue")
      .def("get", &HostValue::get).def("set", &HostValue::set)
      .def("keys", [](HostValue &value) { return value.with([&](Bridge &bridge) {
          return without_gil([&] { return bridge.keys(value.handle->value()); });
      }); })
      .def("call", &HostValue::call, py::arg("this") = py::none())
      .def("to_python", &HostValue::python).def("close", &HostValue::close)
      .def_readonly("closed", &HostValue::closed);
}
} // namespace binding
