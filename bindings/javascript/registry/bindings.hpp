#pragma once
#include "attachments.hpp"
namespace binding {
inline void register_api(py::module_ &module) {
    py::class_<HostAPI, std::shared_ptr<HostAPI>>(module, "_API")
        .def(py::init<std::string>()).def("check", [](HostAPI &api) { api.check(); })
        .def("register", &HostAPI::update).def("unregister", &HostAPI::remove)
        .def("attach", &HostAPI::attach).def("detach", &HostAPI::detach)
        .def("close", &HostAPI::close).def_readonly("closed", &HostAPI::closed);
}
} // namespace binding
