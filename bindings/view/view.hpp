#pragma once
#include <map>
#include "../python/references.hpp"
#include <optional>
namespace binding {
struct HostRuntime;
struct HostSession;
struct HostValue;
namespace objects { struct Session; }
struct HostView : std::enable_shared_from_this<HostView> {
    std::optional<ulbind17::ManagedView> view;
    std::weak_ptr<HostRuntime> runtime;
    std::shared_ptr<HostSession> session;
    bool closed = false;
    Ref close_callback;
    std::map<std::string, std::function<void(Bridge &)>> installers;
    std::map<std::string, std::function<void()>> attachment_cleanup;
    void check(bool require_open = true) const;
    void close();
    void defer_close() {
        auto self = shared_from_this();
        auto &queue = cleanup();
        std::lock_guard lock(queue.mutex);
        queue.tasks.push_back([self] { if (!self->closed) self->close(); });
    }
    void callbacks(py::dict values) {
        check();
        ulbind17::ViewCallbacks callbacks;
        auto frame_callback = [&](const char *name) -> std::function<void(const ulbind17::FrameEvent &)> {
            if (!values.contains(name) || values[name].is_none()) return {};
            auto callback = reference(values[name]);
            return [callback](const auto &event) {
                py::gil_scoped_acquire gil;
                try { callback->object()(py::cast(event, py::return_value_policy::copy)); }
                catch (py::error_already_set &error) { throw Error(Code::HostException, error.what()); }
            };
        };
        callbacks.begin_loading = frame_callback("begin_loading");
        auto external_ready = frame_callback("window_ready");
        callbacks.window_ready = [weak = weak_from_this(), external_ready](const auto &event) {
            py::gil_scoped_acquire gil;
            auto self = weak.lock();
            if (!self || self->closed) return;
            if (event.is_main_frame) {
                auto pending = self->installers;
                for (auto &[name, install] : pending) {
                    if (self->closed) break;
                    if (self->installers.contains(name)) self->view->WithBridge(install);
                }
            }
            if (!self->closed && external_ready) external_ready(event);
        };
        callbacks.dom_ready = frame_callback("dom_ready");
        callbacks.finish_loading = frame_callback("finish_loading");
        if (values.contains("page_settled") && !values["page_settled"].is_none()) {
            auto callback = reference(values["page_settled"]);
            callbacks.page_settled = [callback](std::string_view url) {
                py::gil_scoped_acquire gil;
                try { callback->object()(py::str(url.data(), url.size())); }
                catch (py::error_already_set &error) { throw Error(Code::HostException, error.what()); }
            };
        }
        if (values.contains("fail_loading") && !values["fail_loading"].is_none()) {
            auto callback = reference(values["fail_loading"]);
            callbacks.fail_loading = [callback](const auto &event) {
                py::gil_scoped_acquire gil;
                try { callback->object()(py::cast(event, py::return_value_policy::copy)); }
                catch (py::error_already_set &error) { throw Error(Code::HostException, error.what()); }
            };
        }
        if (values.contains("console") && !values["console"].is_none()) {
            auto callback = reference(values["console"]);
            callbacks.console = [callback](const ultralight::ConsoleMessage &message) {
                py::gil_scoped_acquire gil;
                py::dict event;
                event["message"] = utf8(message.message());
                event["source"] = static_cast<int>(message.source());
                event["type"] = static_cast<int>(message.type());
                event["level"] = static_cast<int>(message.level());
                event["source_url"] = utf8(message.source_id());
                event["line"] = message.line_number(); event["column"] = message.column_number();
                try { callback->object()(event); }
                catch (py::error_already_set &error) { throw Error(Code::HostException, error.what()); }
            };
        }
        view->SetCallbacks(std::move(callbacks));
    }
    py::dict copy_pixels();
    std::shared_ptr<HostValue> evaluate(std::string source);
    std::shared_ptr<objects::Session> bind_object(std::string name, py::object value, py::object members);
    void unbind(std::string name);
};
} // namespace binding
