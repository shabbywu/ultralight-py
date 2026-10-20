#pragma once
#include "../value.hpp"
#include <map>
#include <atomic>
#include <unordered_map>
namespace binding::objects {
struct Document;
struct Session;
// Accessed on the document owner thread; payloads only carry weak references.
inline std::map<Bridge *, std::weak_ptr<Document>> documents;
struct Node {
    Ref object;
    Ref members;
    std::weak_ptr<Session> session;
    std::unique_ptr<Bridge::Handle> proxy;
};
struct Session : std::enable_shared_from_this<Session> {
    std::weak_ptr<Document> document;
    std::atomic_bool closed = false;
    std::string name;
    std::map<std::string, std::shared_ptr<Node>> nodes;
    // Nodes own the Python objects; this index only shortcuts repeated exports.
    std::unordered_map<PyObject *, std::weak_ptr<Node>> exact_containers;
    std::vector<std::shared_ptr<Ref>> cursors;
    std::map<void *, std::function<void()>> async_cleanup;
    JSValueRef root = nullptr;
    void check() const;
    void invalidate() noexcept {
        closed = true;
        auto pending = std::exchange(async_cleanup, {});
        for (auto &[key, cancel] : pending) { try { cancel(); } catch (...) {} }
        exact_containers.clear();
        nodes.clear();
        for (auto &cursor : cursors) cursor->reset();
        cursors.clear();
        root = nullptr;
    }
    void close();
    // Borrow only after checking the session. The owning Node retains the proxy.
    JSValueRef cached_container(py::handle value) const {
        if (PyList_CheckExact(value.ptr()) || PyDict_CheckExact(value.ptr())) {
            auto found = exact_containers.find(value.ptr());
            if (found != exact_containers.end()) {
                if (auto node = found->second.lock()) return node->proxy->value();
            }
        }
        return nullptr;
    }
    std::unique_ptr<Bridge::Handle> convert(Bridge &, py::handle, py::handle members = py::none());
};
struct Document : std::enable_shared_from_this<Document> {
    std::weak_ptr<Bridge> bridge;
    std::weak_ptr<HostView> view;
    Ref containers;
    Bridge *registry_key = nullptr;
    Ref policy;
    std::unique_ptr<Bridge::Handle> factory;
    std::shared_ptr<Session> implicit;
    std::map<std::string, std::shared_ptr<Session>> bindings;
    ~Document() {
        auto entry = documents.find(registry_key);
        if (entry != documents.end() && entry->second.expired()) documents.erase(entry);
        if (implicit) implicit->invalidate();
        for (auto &[name, session] : bindings) session->invalidate();
    }
    std::shared_ptr<Session> session() {
        auto value = std::make_shared<Session>(); value->document = shared_from_this(); return value;
    }
    std::shared_ptr<Node> find(JSValueRef value) {
        auto b = bridge.lock();
        if (!b || !JSValueIsObject(b->context(), value)) return {};
        const JSValueRef args[] = {value};
        auto token = invoke(*b, "lookup", args);
        auto payload = b->unwrap<std::weak_ptr<Node>>(token->value());
        if (!payload) return {};
        auto node = payload->lock();
        if (!node) throw Error(Code::PageGone, "Python binding has been revoked");
        auto scope = node->session.lock();
        if (!scope || scope->closed) throw Error(Code::PageGone, "Python binding has been revoked");
        return node;
    }
    std::unique_ptr<Bridge::Handle> invoke(Bridge &b, const char *name, std::span<const JSValueRef> args) {
        auto fn = get_property(b, factory->value(), name);
        return without_gil([&] { return b.retain(b.call(JSValueToObject(b.context(), fn->value(), nullptr), args)); });
    }
};
inline std::shared_ptr<Document> document(Bridge &, std::shared_ptr<HostView> = {});
inline void Session::check() const {
    if (closed) throw Error(Code::PageGone, "Python binding has been revoked");
    auto doc = document.lock();
    auto b = doc ? doc->bridge.lock() : nullptr;
    if (!b || !b->active()) throw Error(Code::PageGone, "Python binding document expired");
    (void)b->context();
}
inline void Session::close() {
    // Thread checks apply even to an already closed binding.
    if (!PyGILState_Check()) throw Error(Code::WrongThread, "Python binding requires the Python main thread");
    if (closed) return;
    check();
    auto doc = document.lock(); auto b = doc->bridge.lock();
    auto previous_root = b->retain(root);
    auto previous = previous_root->value();
    auto label = name;
    invalidate();
    if (!label.empty()) {
        auto found = doc->bindings.find(label);
        if (found != doc->bindings.end() && found->second.get() == this) doc->bindings.erase(found);
        ulbind17::jsc::Traversal walk;
        auto key = copy_to_js(*b, py::str(label), walk);
        const JSValueRef args[] = {key->value(), previous};
        doc->invoke(*b, "remove", args);
    }
}
} // namespace binding::objects
