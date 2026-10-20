#pragma once
#include "objects/document.hpp"
namespace binding {
inline void register_javascript(py::module_ &module) {
  py::class_<objects::Delivery, std::shared_ptr<objects::Delivery>>(module, "_AsyncDelivery")
      .def("close", &objects::Delivery::close)
      .def("settle", &objects::Delivery::settle)
      .def("on_cancel", [](objects::Delivery &d, py::object cb) { d.cancel = reference(cb); });
  py::class_<objects::Session, std::shared_ptr<objects::Session>>(module, "_PythonBinding")
      .def("close", &objects::Session::close).def("check", &objects::Session::check)
      .def_property_readonly("closed", [](const objects::Session &scope) { return scope.closed.load(); });
  py::class_<PromiseWatch, std::shared_ptr<PromiseWatch>>(module, "_PromiseWatch")
      .def("close", &PromiseWatch::close);
  py::class_<HostValue, std::shared_ptr<HostValue>>(module, "_JSValue")
      .def("watch", &HostValue::watch)
      .def("is_promise", [](HostValue &v) { return v.with([&](Bridge &b) { return b.isPromise(v.handle->value()); }); })
      .def("get", &HostValue::get).def("set", &HostValue::set)
      .def("keys", [](HostValue &value) { return value.with([&](Bridge &bridge) {
          return without_gil([&] { return bridge.keys(value.handle->value()); });
      }); })
      .def("call", &HostValue::call, py::arg("this") = py::none())
      .def("container", &HostValue::container)
      .def("to_python", &HostValue::python, py::kw_only(), py::arg("copy") = false)
      .def("close", &HostValue::close)
      .def_property_readonly("closed", &HostValue::is_closed);
}
} // namespace binding
