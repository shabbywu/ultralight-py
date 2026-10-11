#pragma once
#include "filesystem.hpp"
namespace binding {
inline void register_resources(py::module_ &module) {
  py::class_<Resource>(module, "Resource")
      .def(py::init([](py::bytes data, py::object mime, std::string charset) {
          return Resource{data.cast<std::string>(), mime.is_none() ? "" : mime.cast<std::string>(), std::move(charset)};
      }), py::arg("data"), py::arg("mime_type") = py::none(), py::arg("charset") = "utf-8")
      .def_property_readonly("data", [](const Resource &value) { return py::bytes(value.data); })
      .def_readonly("mime_type", &Resource::mime_type).def_readonly("charset", &Resource::charset);
}
} // namespace binding
