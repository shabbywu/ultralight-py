#pragma once
#include "javascript.hpp"
namespace binding {
inline void register_view(py::module_ &module) {
  py::class_<ulbind17::FrameEvent>(module, "FrameEvent")
      .def_readonly("frame_id", &ulbind17::FrameEvent::frame_id)
      .def_readonly("is_main_frame", &ulbind17::FrameEvent::is_main_frame)
      .def_readonly("url", &ulbind17::FrameEvent::url);
  py::class_<ulbind17::LoadFailure>(module, "LoadFailure")
      .def_readonly("frame", &ulbind17::LoadFailure::frame)
      .def_readonly("description", &ulbind17::LoadFailure::description)
      .def_readonly("domain", &ulbind17::LoadFailure::domain)
      .def_readonly("code", &ulbind17::LoadFailure::code);
  py::class_<HostView, std::shared_ptr<HostView>>(module, "_View")
      .def("load_html", [](HostView &host, std::string html, std::string url) {
          host.check(); py::gil_scoped_release release; host.view->LoadHTML(html, url);
      })
      .def("load_url", [](HostView &host, std::string url) {
          host.check(); py::gil_scoped_release release; host.view->LoadURL(url);
      })
      .def("resize", [](HostView &host, uint32_t width, uint32_t height) {
          host.check(); py::gil_scoped_release release; host.view->Resize(width, height);
      })
      .def("set_callbacks", &HostView::callbacks)
      .def("evaluate_handle", &HostView::evaluate)
      .def("bind_function", &HostView::bind_function)
      .def("copy_pixels", [](HostView &host) {
          host.check(); ulbind17::PixelBuffer pixels;
          { py::gil_scoped_release release; pixels = host.view->CopyPixels(); }
          py::dict result;
          result["width"] = pixels.width; result["height"] = pixels.height;
          result["row_bytes"] = pixels.row_bytes;
          result["format"] = "BGRA8Premultiplied";
          const auto &rect = pixels.dirty_bounds;
          result["dirty_bounds"] = py::make_tuple(rect.left, rect.top, rect.right, rect.bottom);
          result["data"] = py::bytes(reinterpret_cast<const char *>(pixels.data.data()), pixels.data.size());
          return result;
      })
      .def("clear_dirty_bounds", [](HostView &host) { host.check(); host.view->ClearDirtyBounds(); })
      .def("close", &HostView::close).def("_defer_close", &HostView::defer_close)
      .def_readonly("closed", &HostView::closed);
}
} // namespace binding
