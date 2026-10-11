#pragma once
#include "errors.hpp"
#include "references.hpp"
#include "../javascript/conversion.hpp"
namespace binding {
inline void register_python(py::module_ &module) {
  py::enum_<Code>(module, "ErrorCode")
      .value("InvalidArgument", Code::InvalidArgument).value("WrongThread", Code::WrongThread)
      .value("Closed", Code::Closed).value("Busy", Code::Busy).value("PageGone", Code::PageGone)
      .value("CrossContext", Code::CrossContext).value("ScriptException", Code::ScriptException)
      .value("HostException", Code::HostException).value("Unsupported", Code::Unsupported)
      .value("TypeMismatch", Code::TypeMismatch).value("TraversalLimit", Code::TraversalLimit);
  error_type = PyErr_NewException("ultralight_py.UltralightError", PyExc_RuntimeError, nullptr);
  module.add_object("UltralightError", py::reinterpret_steal<py::object>(error_type));
  script_error_type = PyErr_NewException("ultralight_py.JavaScriptError", error_type, nullptr);
  module.add_object("JavaScriptError", py::reinterpret_steal<py::object>(script_error_type));
  py::register_local_exception_translator([](std::exception_ptr exception) {
      try { if (exception) std::rethrow_exception(exception); }
      catch (const Error &error) {
          auto object = error_object(error);
          PyErr_SetObject(error.code == Code::ScriptException ? script_error_type : error_type, object.ptr());
      }
  });
  py::class_<Undefined>(module, "_Undefined").def("__repr__", [](const Undefined &) { return "undefined"; });
  module.attr("undefined") = py::cast(Undefined{});
  undefined = module.attr("undefined").ptr();
  module.def("_drain", &drain);
  module.def("_make_error", [](Code code, std::string message) { return error_object(Error(code, std::move(message))); });
  module.def("_report_unraisable", [](py::object error) {
      PyErr_SetObject(reinterpret_cast<PyObject *>(Py_TYPE(error.ptr())), error.ptr());
      PyErr_WriteUnraisable(Py_None);
  });}
} // namespace binding
