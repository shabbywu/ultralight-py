#pragma once
#include "runtime.hpp"
#include "../view/view.hpp"
#include <algorithm>
namespace binding {
// Runtime/View ownership and thread checks require both types to be complete.
inline void HostView::check(bool require_open) const {
    auto host = runtime.lock();
    if (!host) throw Error(Code::Closed, "Runtime is closed");
    host->check(false);
    if (require_open && (closed || host->closed)) throw Error(Code::Closed, "View is closed");
}

inline void HostView::close() {
    check(false);
    if (closed) return;
    // Keep this wrapper alive while removing Runtime's ownership, including
    // deferred close and callbacks that close their own View.
    auto self = shared_from_this();
    closed = true;
    if (auto host = runtime.lock()) std::erase(host->views, self);
    { py::gil_scoped_release release; view->Close(); view.reset(); }
}

inline std::shared_ptr<HostView> HostRuntime::create_view(uint32_t width, uint32_t height, bool transparent) {
    check();
    auto result = std::make_shared<HostView>(); result->runtime = shared_from_this();
    ultralight::ViewConfig config; config.is_accelerated = false; config.is_transparent = transparent;
    { py::gil_scoped_release release; result->view.emplace(runtime->CreateView(width, height, config)); }
    views.push_back(result); return result;
}
inline void HostRuntime::close() {
    check(false);
    if (closed) return;
    // A resource resolver is forbidden to reenter us, so no active resolver can
    // wait on this close while we wait for it to finish.
    { py::gil_scoped_release release; resources->stop(); }
    closed = true;
    auto alive = std::exchange(views, {});
    for (auto &view : alive) view->close();
    { py::gil_scoped_release release; runtime->Close(); runtime.reset(); }
    flush_errors(); error_handler.reset();
}
} // namespace binding
