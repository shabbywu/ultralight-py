#pragma once
#include "conversion.hpp"
namespace binding {
inline void register_images(pybind11::module_ &module) {
    namespace py = pybind11;
    module.def("_bgra_to_rgba", &bgra_to_rgba,
               py::arg("data"), py::arg("width"), py::arg("height"), py::arg("row_bytes"));
}
} // namespace binding
