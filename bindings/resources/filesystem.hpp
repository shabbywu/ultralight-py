#pragma once
#include "../python/references.hpp"
#include <ulbind17/setup.hpp>
#include <ulbind17/resources/FileSystemOverlay.hpp>
#include <condition_variable>
#include <optional>
namespace binding {
inline thread_local bool in_resource_callback = false;
struct Resource {
    std::string data, mime_type, charset;
};
struct ResourceState {
    std::mutex mutex;
    std::condition_variable idle;
    Ref loader;
    bool closing = false;
    std::size_t active = 0;
    std::vector<Error> errors;
    void stop() {
        std::unique_lock lock(mutex);
        closing = true;
        idle.wait(lock, [&] { return active == 0; });
        loader.reset();
    }
};
class PythonFileSystem : public ulbind17::platform::FileSystem {
    std::shared_ptr<ResourceState> state_;
    ulbind17::resources::embedded::SDKResources embedded_;
    template <typename T, typename F> T safely(F &&callback, T fallback) noexcept {
        try { return std::forward<F>(callback)(); }
        catch (const std::exception &exception) {
            try {
                std::lock_guard lock(state_->mutex);
                state_->errors.emplace_back(Code::HostException, exception.what());
            } catch (...) {} // Allocation failure must not escape an SDK worker.
        } catch (...) {}
        return fallback;
    }
    std::optional<Resource> resolve(const ultralight::String &path, bool &failed) {
        Ref callback;
        {
            std::lock_guard lock(state_->mutex);
            if (state_->closing) { failed = true; return {}; }
            if (!state_->loader || embedded_.FileExists(path)) return {};
            callback = state_->loader; ++state_->active;
        }
        struct Done {
            ResourceState &state;
            Ref callback;
            ~Done() {
                callback.reset();
                std::lock_guard lock(state.mutex); --state.active; state.idle.notify_all();
            }
        } done{*state_, std::move(callback)};
        py::gil_scoped_acquire gil;
        struct Scope {
            bool previous = in_resource_callback;
            Scope() { in_resource_callback = true; }
            ~Scope() { in_resource_callback = previous; }
        } scope;
        try {
            auto result = done.callback->object()(py::str(utf8(path)));
            if (result.is_none()) return {};
            if (py::isinstance<py::bytes>(result)) return Resource{result.cast<std::string>(), "", "utf-8"};
            if (py::isinstance<Resource>(result)) return result.cast<Resource>();
            throw py::type_error("resource_loader must return bytes, Resource, or None");
        } catch (const std::exception &exception) {
            failed = true;
            std::lock_guard lock(state_->mutex);
            state_->errors.emplace_back(Code::HostException, exception.what());
            return {};
        }
    }
  public:
    PythonFileSystem(std::string root, std::shared_ptr<ResourceState> state)
        : ulbind17::platform::FileSystem(std::move(root)), state_(std::move(state)), embedded_("resources/") {}
    bool FileExists(const ultralight::String &path) override {
        return safely([&] {
            bool failed = false;
            auto value = resolve(path, failed);
            return value.has_value() || (!failed && ulbind17::platform::FileSystem::FileExists(path));
        }, false);
    }
    ultralight::RefPtr<ultralight::Buffer> OpenFile(const ultralight::String &path) override {
        return safely([&]() -> ultralight::RefPtr<ultralight::Buffer> {
            bool failed = false;
            auto value = resolve(path, failed);
            if (value) return ultralight::Buffer::CreateFromCopy(value->data.data(), value->data.size());
            return failed ? nullptr : ulbind17::platform::FileSystem::OpenFile(path);
        }, ultralight::RefPtr<ultralight::Buffer>{});
    }
    ultralight::String GetFileMimeType(const ultralight::String &path) override {
        return safely([&] {
            bool failed = false;
            auto value = resolve(path, failed);
            if (value && !value->mime_type.empty()) return ultralight::String(value->mime_type.data(), value->mime_type.size());
            return ulbind17::platform::FileSystem::GetFileMimeType(path);
        }, ultralight::String("application/unknown"));
    }
    ultralight::String GetFileCharset(const ultralight::String &path) override {
        return safely([&] {
            bool failed = false;
            auto value = resolve(path, failed);
            return value ? ultralight::String(value->charset.data(), value->charset.size()) : ultralight::String("utf-8");
        }, ultralight::String("utf-8"));
    }
};
} // namespace binding
