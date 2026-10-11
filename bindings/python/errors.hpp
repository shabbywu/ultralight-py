#pragma once
#include "../common.hpp"
namespace binding {
inline PyObject *error_type = nullptr, *script_error_type = nullptr;
inline py::object error_object(const Error &error) {
    auto result = py::reinterpret_borrow<py::object>(
        error.code == Code::ScriptException ? script_error_type : error_type)(error.what());
    result.attr("code") = py::cast(error.code);
    result.attr("stack") = error.stack;
    result.attr("source_url") = error.source_url;
    result.attr("line") = error.line;
    result.attr("column") = error.column;
    return result;
}
} // namespace binding
