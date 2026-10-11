#pragma once
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <ulbind17/runtime.hpp>

namespace binding {
namespace py = pybind11;
using Bridge = ulbind17::jsc::Bridge;
using Error = ulbind17::Error;
using Code = ulbind17::ErrorCode;

inline std::string utf8(const ultralight::String &text) {
    auto data = text.utf8(); return {data.data(), data.length()};
}
template <typename F> decltype(auto) without_gil(F &&callback) {
    py::gil_scoped_release release;
    return std::forward<F>(callback)();
}
} // namespace binding
