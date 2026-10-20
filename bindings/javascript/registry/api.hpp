#pragma once
#include "../../view/javascript.hpp"
namespace binding {
struct HostAPI : std::enable_shared_from_this<HostAPI> {
    struct Entry { Ref object, members; };
    struct Attachment {
        bool retired = false;
        std::weak_ptr<HostView> view;
        std::weak_ptr<objects::Document> document;
        std::unique_ptr<Bridge::Handle> root;
        std::map<std::string, std::shared_ptr<objects::Session>> scopes;
    };
    std::string name;
    bool closed = false;
    const std::thread::id owner = std::this_thread::get_id();
    std::map<std::string, Entry> entries;
    std::map<HostView *, std::shared_ptr<Attachment>> attachments;
    explicit HostAPI(std::string name) : name(std::move(name)) {}
    void check(bool open = true) const {
        if (std::this_thread::get_id() != owner) throw Error(Code::WrongThread, "API requires the Python main thread");
        if (in_resource_callback) throw Error(Code::Busy, "Resource callbacks cannot operate on API");
        if (open && closed) throw Error(Code::Closed, "API is closed");
    }
    std::string key(const std::string &entry) const {
        return "\x1f" + std::to_string(reinterpret_cast<uintptr_t>(this)) + ":" + entry;
    }
    void revoke(Attachment &attached, const std::string &entry);
    void forget(HostView *view);
    void install(HostView *target, Bridge &bridge);
    void install_entry(Attachment &attached, Bridge &bridge, const std::shared_ptr<objects::Document> &doc,
                       const std::string &entry, const Entry &value);
    void attach(const std::shared_ptr<HostView> &view);
    void detach(const std::shared_ptr<HostView> &view);
    void update(std::string entry, py::object object, py::object members) {
        check(); entries[entry] = {reference(object), reference(members)};
        std::vector<std::shared_ptr<HostView>> targets;
        for (auto &[target, attached] : attachments) if (auto view = attached->view.lock()) targets.push_back(view);
        std::exception_ptr failure;
        for (auto &view : targets) {
            try {
                if (view->closed || !attachments.contains(view.get())) continue;
                view->view->WithBridge([&](Bridge &bridge) {
                    auto lifetime = attachments.at(view.get());
                    auto &attached = *lifetime;
                    auto doc = objects::document(bridge, view);
                    if (attached.document.lock() != doc || !attached.root) install(view.get(), bridge);
                    else {
                        auto definition = entries.at(entry);
                        install_entry(attached, bridge, doc, entry, definition);
                    }
                });
            } catch (...) { if (!failure) failure = std::current_exception(); }
        }
        if (failure) std::rethrow_exception(failure);
    }
    void remove(std::string entry) {
        check(); entries.erase(entry);
        std::vector<std::shared_ptr<Attachment>> pending;
        for (auto &[target, attached] : attachments) pending.push_back(attached);
        std::exception_ptr failure;
        for (auto &lifetime : pending) {
            auto &attached = *lifetime;
            auto view = attached.view.lock();
            try {
                auto scope = attached.scopes.find(entry);
                if (view && !view->closed && scope != attached.scopes.end()) {
                    view->view->WithBridge([&](Bridge &bridge) {
                        auto doc = attached.document.lock();
                        if (!doc || doc->bridge.lock().get() != &bridge) return;
                        ulbind17::jsc::Traversal walk;
                        auto label = copy_to_js(bridge, py::str(entry), walk);
                        const JSValueRef args[] = {attached.root->value(), label->value(), scope->second->root};
                        doc->invoke(bridge, "unregister", args);
                    });
                }
            } catch (...) { if (!failure) failure = std::current_exception(); }
            revoke(attached, entry);
        }
        if (failure) std::rethrow_exception(failure);
    }
    void close() {
        check(false); if (closed) return;
        std::vector<std::shared_ptr<HostView>> targets;
        for (auto &[target, attached] : attachments) if (auto view = attached->view.lock()) targets.push_back(view);
        std::exception_ptr failure;
        for (auto &view : targets) {
            try { detach(view); }
            catch (...) {
                forget(view.get()); view->installers.erase(name); view->attachment_cleanup.erase(name);
                if (!failure) failure = std::current_exception();
            }
        }
        closed = true; attachments.clear(); entries.clear();
        if (failure) std::rethrow_exception(failure);
    }
};
} // namespace binding
