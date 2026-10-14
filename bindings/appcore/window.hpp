#pragma once
#include "../runtime/views.hpp"
#include <ulbind17/appcore.hpp>
namespace binding {
struct HostWindow : std::enable_shared_from_this<HostWindow> {
    std::optional<ulbind17::appcore::Window> window;
    std::shared_ptr<HostRuntime> runtime;
    std::shared_ptr<HostView> view;
    Ref callback;
    bool closed = false;
    void check(bool open = true) const {
        runtime->check(false);
        if (open && (closed || runtime->closed)) throw Error(Code::Closed, "Window is closed");
    }
    void emit(const char *event, py::object value) {
        auto current = callback;
        if (!current) return;
        try { current->object()(event, std::move(value)); }
        catch (py::error_already_set &error) { runtime->report(Error(Code::HostException, error.what())); }
    }
    void did_close() {
        py::gil_scoped_acquire gil;
        if (closed) return;
        closed = true;
        if (view) view->close();
        emit("closed", py::none()); callback.reset();
    }
    void close() {
        check(false); if (closed) return;
        auto native = *window;
        { py::gil_scoped_release release; native.Close(); }
        did_close();
        window.reset();
    }
    void set_callback(py::object value) {
        check(); callback = reference(value);
        auto weak = weak_from_this();
        window->SetCallbacks({[weak] { if (auto self = weak.lock()) self->did_close(); },
                              [weak](double width, double height) {
                                  py::gil_scoped_acquire gil;
                                  if (auto self = weak.lock()) self->emit("resized", py::make_tuple(width, height));
                              }});
    }
};
} // namespace binding
