#include "python/bindings.hpp"
#include "resources/bindings.hpp"
#include "runtime/bindings.hpp"
#include "view/bindings.hpp"
#include "javascript/bindings.hpp"
#include "input/bindings.hpp"

PYBIND11_MODULE(_native, module) {
  module.doc() = "Python bindings for Ultralight.";
  binding::register_python(module);
  binding::register_resources(module);
  binding::register_runtime(module);
  binding::register_view(module);
  binding::register_javascript(module);
  binding::register_input(module);
}
