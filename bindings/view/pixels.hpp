#pragma once
#include "../runtime/views.hpp"
namespace binding {
inline py::dict HostView::copy_pixels() {
    check(); ulbind17::PixelBuffer pixels;
    { py::gil_scoped_release release; pixels = view->CopyPixels(); }
    py::dict result;
    result["width"] = pixels.width; result["height"] = pixels.height;
    result["row_bytes"] = pixels.row_bytes;
    result["format"] = "BGRA8Premultiplied";
    const auto &rect = pixels.dirty_bounds;
    result["dirty_bounds"] = py::make_tuple(rect.left, rect.top, rect.right, rect.bottom);
    result["data"] = py::bytes(reinterpret_cast<const char *>(pixels.data.data()), pixels.data.size());
    return result;
}
} // namespace binding
