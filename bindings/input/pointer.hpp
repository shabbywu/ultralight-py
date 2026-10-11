#pragma once
#include "common.hpp"
namespace binding {
inline void mouse_event(HostView &host, int type, int x, int y, int button) {
    if (type < 0 || type > 2 || button < 0 || button > 5 || (type != 0 && button == 0))
        throw py::value_error("Invalid mouse event type or button");
    ultralight::MouseEvent event{static_cast<ultralight::MouseEvent::Type>(type), x, y,
                               static_cast<ultralight::MouseEvent::Button>(button)};
    with_input(host, [&](auto &view) { view.FireMouseEvent(event); });
}
inline void scroll_event(HostView &host, int type, int dx, int dy, int x, int y) {
    if (type < 0 || type > 1) throw py::value_error("Invalid scroll event type");
    ultralight::ScrollEvent event{static_cast<ultralight::ScrollEvent::Type>(type), dx, dy, x, y};
    with_input(host, [&](auto &view) { view.FireScrollEvent(event); });
}
} // namespace binding
