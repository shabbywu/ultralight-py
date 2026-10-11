#include <pybind11/pybind11.h>

PYBIND11_MODULE(_native, module) {
  module.doc() = "Python bindings for Ultralight.";
}
