#pragma once
#include "../resources/filesystem.hpp"
#include "../python/errors.hpp"
namespace binding {
struct HostView;
struct HostRuntime : std::enable_shared_from_this<HostRuntime> {
    std::optional<ulbind17::Runtime> runtime;
    std::shared_ptr<ResourceState> resources = std::make_shared<ResourceState>();
    std::vector<std::shared_ptr<HostView>> views;
    Ref error_handler;
    const std::thread::id owner = std::this_thread::get_id();
    bool closed = false;
    void check(bool require_open = true) const {
        if (in_resource_callback) throw Error(Code::Busy, "Resource callbacks cannot operate on Runtime/View/JS");
        if (std::this_thread::get_id() != owner) throw Error(Code::WrongThread, "Operation requires the Python main thread");
        if (require_open && closed) throw Error(Code::Closed, "Runtime is closed");
    }
    static std::shared_ptr<HostRuntime> create(std::string root, py::object loader) {
        if (in_resource_callback) throw Error(Code::Busy, "Resource callbacks cannot create a Runtime");
        auto threading = py::module_::import("threading");
        if (!threading.attr("current_thread")().is(threading.attr("main_thread")()))
            throw Error(Code::WrongThread, "Runtime must be created on the Python main thread");
        auto host = std::make_shared<HostRuntime>();
        if (!loader.is_none()) host->resources->loader = reference(loader);
        ulbind17::setup_ultralight_platform();
        using Overlay = ulbind17::resources::FileSystemOverlay<ulbind17::resources::embedded::SDKResources>;
        // Platform stores borrowed pointers; these native-only services survive
        // until process exit, but stop() removes every Python reference.
        static std::shared_ptr<Overlay> services;
        services = std::make_shared<Overlay>(ulbind17::resources::embedded::SDKResources("resources/"),
                                            std::make_shared<PythonFileSystem>(std::move(root), host->resources));
        ultralight::Platform::instance().set_file_system(services.get());
        {
            py::gil_scoped_release release;
            host->runtime.emplace(ulbind17::Runtime::Create());
        }
        host->runtime->SetErrorHandler([weak = std::weak_ptr(host)](const Error &error) {
            if (auto host = weak.lock()) host->report(error);
        });
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
    std::shared_ptr<HostView> create_view(uint32_t width, uint32_t height, bool transparent);
};
} // namespace binding
