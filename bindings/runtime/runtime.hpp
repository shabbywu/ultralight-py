#pragma once
#include "../resources/filesystem.hpp"
#include "../python/errors.hpp"
namespace binding {
struct HostView;
struct HostSession;
struct HostRuntime : std::enable_shared_from_this<HostRuntime> {
    std::optional<ulbind17::Runtime> runtime;
    std::shared_ptr<ResourceState> resources = std::make_shared<ResourceState>();
    std::vector<std::shared_ptr<HostView>> views;
    std::vector<std::shared_ptr<HostSession>> sessions;
    Ref error_handler;
    const std::thread::id owner = std::this_thread::get_id();
    bool closed = false;
    void check(bool require_open = true) const {
        if (in_resource_callback) throw Error(Code::Busy, "Resource callbacks cannot operate on Runtime/View/JS");
        if (std::this_thread::get_id() != owner) throw Error(Code::WrongThread, "Operation requires the Python main thread");
        if (require_open && closed) throw Error(Code::Closed, "Runtime is closed");
    }
    static std::shared_ptr<HostRuntime> prepare(std::string root, py::object loader) {
        if (in_resource_callback) throw Error(Code::Busy, "Resource callbacks cannot create a Runtime");
        auto threading = py::module_::import("threading");
        if (!threading.attr("current_thread")().is(threading.attr("main_thread")()))
            throw Error(Code::WrongThread, "Runtime must be created on the Python main thread");
        auto host = std::make_shared<HostRuntime>();
        if (!loader.is_none()) host->resources->loader = reference(loader);
        return host;
    }
    static void prepare_file_system(const std::shared_ptr<HostRuntime> &host, std::string root) {
        using Overlay = ulbind17::resources::FileSystemOverlay<ulbind17::resources::embedded::SDKResources>;
        // The Platform borrows these services until process exit.
        static std::shared_ptr<Overlay> services;
        services = std::make_shared<Overlay>(ulbind17::resources::embedded::SDKResources("resources/"),
                                            std::make_shared<PythonFileSystem>(std::move(root), host->resources));
        ultralight::Platform::instance().set_file_system(services.get());
    }
    void install_error_handler() {
        runtime->SetErrorHandler([weak = weak_from_this()](const Error &error) {
            if (auto host = weak.lock()) host->report(error);
        });
    }
    static std::shared_ptr<HostRuntime> create(std::string root, py::object loader, std::string cache_path) {
        auto host = prepare(root, std::move(loader));
        ultralight::Config config;
        config.cache_path = cache_path.c_str();
        ulbind17::setup_ultralight_platform(&config);
        // setup installs its own FileSystem; restore our resource overlay.
        prepare_file_system(host, std::move(root));
        { py::gil_scoped_release release; host->runtime.emplace(ulbind17::Runtime::Create()); }
        host->install_error_handler();
        return host;
    }
    void report(const Error &error) {
        py::gil_scoped_acquire gil;
        auto handler = error_handler;
        if (!handler) return;
        try { handler->object()(error_object(error)); }
        catch (py::error_already_set &exception) { exception.discard_as_unraisable("ultralight_py error handler"); }
    }
    void flush_errors() {
        std::vector<Error> errors;
        { std::lock_guard lock(resources->mutex); errors.swap(resources->errors); }
        for (auto &error : errors) report(error);
    }
    void close();
    std::shared_ptr<HostView> create_view(uint32_t width, uint32_t height, bool transparent, std::shared_ptr<HostSession> session = nullptr);
    std::shared_ptr<HostView> create_configured_view(uint32_t width, uint32_t height, const ultralight::ViewConfig &config, std::shared_ptr<HostSession> session);
    std::shared_ptr<HostSession> create_session(std::string name, bool persistent);
};
struct HostSession : std::enable_shared_from_this<HostSession> {
    std::weak_ptr<HostRuntime> runtime;
    ultralight::RefPtr<ultralight::Session> session;
    std::string name, disk_path;
    bool persistent = false, closed = false;
    void check() const {
        auto host = runtime.lock();
        if (!host) throw Error(Code::Closed, "Runtime is closed");
        host->check();
        if (closed) throw Error(Code::Closed, "Session is closed");
    }
    void close(bool force_close = false);
};
} // namespace binding
