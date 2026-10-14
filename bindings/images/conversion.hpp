#pragma once
#include <pybind11/pybind11.h>
#include <algorithm>
#include <cstdint>
#include <limits>
#include <string>

namespace binding {
inline std::size_t image_integer(pybind11::handle value, const char *name,
                                 std::size_t maximum) {
    if (!PyLong_Check(value.ptr()) || PyBool_Check(value.ptr()))
        throw pybind11::type_error(std::string(name) + " must be an integer");
    auto number = PyLong_AsUnsignedLongLong(value.ptr());
    if (PyErr_Occurred()) {
        PyErr_Clear();
        throw pybind11::value_error(std::string(name) + " is out of range");
    }
    if (number == 0 || number > maximum)
        throw pybind11::value_error(std::string(name) + " is out of range");
    return static_cast<std::size_t>(number);
}

inline std::size_t image_product(std::size_t left, std::size_t right) {
    constexpr auto maximum = static_cast<std::size_t>(PY_SSIZE_T_MAX);
    if (left > maximum / right) {
        PyErr_SetString(PyExc_OverflowError, "Image size exceeds the native buffer limit");
        throw pybind11::error_already_set();
    }
    return left * right;
}

inline pybind11::bytes bgra_to_rgba(pybind11::object data, pybind11::object width_value,
                                   pybind11::object height_value, pybind11::object stride_value) {
    namespace py = pybind11;
    if (!PyBytes_Check(data.ptr())) throw py::type_error("data must be bytes");
    constexpr auto dimension_max = std::numeric_limits<std::uint32_t>::max();
    const auto width = image_integer(width_value, "width", dimension_max);
    const auto height = image_integer(height_value, "height", dimension_max);
    const auto stride = image_integer(stride_value, "row_bytes", PY_SSIZE_T_MAX);
    const auto row_size = image_product(width, 4);
    const auto output_size = image_product(row_size, height);
    if (stride < row_size) throw py::value_error("row_bytes must be at least width * 4");
    // Check only bytes actually read: the final row need not include padding.
    const auto preceding = height == 1 ? 0 : image_product(stride, height - 1);
    if (preceding > static_cast<std::size_t>(PY_SSIZE_T_MAX) - row_size) {
        PyErr_SetString(PyExc_OverflowError, "Image size exceeds the native buffer limit");
        throw py::error_already_set();
    }
    if (static_cast<std::size_t>(PyBytes_GET_SIZE(data.ptr())) < preceding + row_size)
        throw py::value_error("data is too short for the image dimensions and stride");
    auto *allocated = PyBytes_FromStringAndSize(nullptr, static_cast<Py_ssize_t>(output_size));
    if (!allocated) throw py::error_already_set();
    auto result = py::reinterpret_steal<py::bytes>(allocated);
    const auto *source = reinterpret_cast<const unsigned char *>(PyBytes_AS_STRING(data.ptr()));
    auto *destination = reinterpret_cast<unsigned char *>(PyBytes_AS_STRING(result.ptr()));
    {
        // Pin input and output until the GIL is reacquired; output is not exposed yet.
        py::gil_scoped_release release;
        for (std::size_t y = 0; y < height; ++y) {
            const auto *row = source + y * stride;
            auto *out = destination + y * row_size;
            for (std::size_t x = 0; x < width; ++x, row += 4, out += 4) {
                const auto alpha = row[3];
                if (alpha == 0) {
                    out[0] = out[1] = out[2] = out[3] = 0;
                } else if (alpha == 255) {
                    out[0] = row[2]; out[1] = row[1]; out[2] = row[0]; out[3] = alpha;
                } else {
                    out[0] = static_cast<unsigned char>(std::min(255u, row[2] * 255u / alpha));
                    out[1] = static_cast<unsigned char>(std::min(255u, row[1] * 255u / alpha));
                    out[2] = static_cast<unsigned char>(std::min(255u, row[0] * 255u / alpha));
                    out[3] = alpha;
                }
            }
        }
    }
    return result;
}
} // namespace binding
