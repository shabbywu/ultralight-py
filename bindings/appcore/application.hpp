#pragma once
#include "window.hpp"
namespace binding {
struct HostApplication : std::enable_shared_from_this<HostApplication> {
    std::optional<ulbind17::appcore::Application> application;
    std::shared_ptr<HostRuntime> runtime;
    bool closed = false;
    void check(bool open = true) const {
        runtime->check(false);
        if (open && (closed || runtime->closed)) throw Error(Code::Closed, "Application is closed");
    }
    static std::shared_ptr<HostApplication> create(std::string root, py::object loader, std::string cache,
                                                 std::string app_name, std::string developer_name, bool cpu) {
        auto result = std::make_shared<HostApplication>();
        result->runtime = HostRuntime::prepare(root, std::move(loader));
        HostRuntime::prepare_file_system(result->runtime, std::move(root));
        ultralight::Settings settings;
        settings.app_name = app_name.c_str(); settings.developer_name = developer_name.c_str();
        settings.force_cpu_renderer = cpu;
        ultralight::Config config; config.cache_path = cache.c_str();
        { py::gil_scoped_release release;
          result->application.emplace(ulbind17::appcore::Application::Create(settings, config));
          result->runtime->runtime.emplace(result->application->runtime()); }
        result->runtime->install_error_handler();
        return result;
    }
    std::shared_ptr<HostWindow> create_window(double width, double height, std::string title,
                                             std::shared_ptr<HostSession> session,
                                             std::shared_ptr<HostView> adopted, bool transparent,
                                             bool resizable, bool fullscreen) {
        check();
        if (adopted) {
            adopted->check();
            if (adopted->runtime.lock() != runtime) throw Error(Code::CrossContext, "View belongs to another Runtime");
            if (session) throw Error(Code::InvalidArgument, "An adopted View already has a Session");
        }
        auto result = std::make_shared<HostWindow>(); result->runtime = runtime;
        auto flags = ultralight::WindowFlags::Titled;
        if (resizable) flags = flags | ultralight::WindowFlags::Resizable;
        { py::gil_scoped_release release; result->window.emplace(application->NewWindow(width, height, fullscreen, flags)); }
        auto native = result->window->native(); native->SetTitle(title.c_str());
        const bool adopting = bool(adopted);
        if (adopted) result->view = std::move(adopted);
        else {
            auto config = native->default_view_config(); config.is_transparent = transparent;
            result->view = runtime->create_configured_view(native->device_width(), native->device_height(), config, session);
        }
        try { py::gil_scoped_release release; result->window->AdoptPanel(*result->view->view); }
        catch (...) {
            if (!adopting && result->view) result->view->close();
            throw;
        }
        return result;
    }
    bool run_once() {
        check(false); if (closed || runtime->closed) { close(); return false; }
        bool running;
        { py::gil_scoped_release release; running = application->RunOnce(0); }
        runtime->flush_errors();
        if (!running) close();
        return running && !closed && !runtime->closed;
    }
    void close() {
        check(false); if (closed) return;
        closed = true;
        runtime->close();
        application.reset();
    }
};
} // namespace binding
