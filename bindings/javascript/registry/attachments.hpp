#pragma once
#include "api.hpp"
namespace binding {
inline void HostAPI::revoke(Attachment &attached, const std::string &entry) {
    auto found = attached.scopes.find(entry);
    if (found == attached.scopes.end()) return;
    found->second->invalidate();
    if (auto doc = attached.document.lock()) doc->bindings.erase(key(entry));
    attached.scopes.erase(found);
}
inline void HostAPI::forget(HostView *view) {
    auto found = attachments.find(view);
    if (found == attachments.end()) return;
    auto attached = found->second;
    attachments.erase(found);
    attached->retired = true;
    auto names = attached->scopes;
    for (auto &[entry, scope] : names) revoke(*attached, entry);
}
inline void HostAPI::install(HostView *target, Bridge &bridge) {
    auto found = attachments.find(target);
    if (found == attachments.end()) return;
    auto lifetime = found->second;
    auto &attached = *lifetime;
    auto doc = objects::document(bridge);
    if (attached.document.lock() != doc) {
        for (auto &[entry, scope] : attached.scopes) scope->invalidate();
        attached.scopes.clear(); attached.root.reset(); attached.document = doc;
    }
    if (!attached.root) {
        ulbind17::jsc::Traversal walk;
        auto label = copy_to_js(bridge, py::str(name), walk);
        const JSValueRef args[] = {label->value()};
        attached.root = doc->invoke(bridge, "namespace", args);
    }
    auto definitions = entries;
    for (auto &[entry, value] : definitions) {
        if (closed || attached.retired || !bridge.active()) break;
        install_entry(attached, bridge, doc, entry, value);
    }
}
inline void HostAPI::install_entry(Attachment &attached, Bridge &bridge, const std::shared_ptr<objects::Document> &doc,
                   const std::string &entry, const Entry &value) {
    auto scope = doc->session();
    auto proxy = scope->convert(bridge, value.object->object(), value.members->object());
    if (closed || attached.retired || !bridge.active()) {
        scope->invalidate();
        throw Error(Code::PageGone, "API attachment closed during registration");
    }
    auto current = entries.find(entry);
    if (current == entries.end() || current->second.object != value.object) return;
    ulbind17::jsc::Traversal walk;
    auto label = copy_to_js(bridge, py::str(entry), walk);
    const JSValueRef args[] = {attached.root->value(), label->value(), proxy->value()};
    doc->invoke(bridge, "register", args);
    revoke(attached, entry);
    scope->root = proxy->value();
    doc->bindings[key(entry)] = scope;
    attached.scopes[entry] = std::move(scope);
}
inline void HostAPI::attach(const std::shared_ptr<HostView> &view) {
    check(); view->check();
    auto existing = view->installers.find(name);
    if (existing != view->installers.end()) {
        if (attachments.contains(view.get())) return;
        throw Error(Code::InvalidArgument, "API namespace is already attached to this View");
    }
    auto attached = std::make_shared<Attachment>(); attached->view = view;
    attachments.emplace(view.get(), std::move(attached));
    auto self = shared_from_this(); auto weak = std::weak_ptr(view);
    view->installers[name] = [self, weak](Bridge &bridge) {
        if (auto target = weak.lock()) self->install(target.get(), bridge);
    };
    view->attachment_cleanup[name] = [self, target = view.get()] { self->forget(target); };
    try { view->view->WithBridge(view->installers.at(name)); }
    catch (...) { detach(view); throw; }
}
inline void HostAPI::detach(const std::shared_ptr<HostView> &view) {
    check(false);
    auto found = attachments.find(view.get());
    if (found == attachments.end()) return;
    if (!view->closed) {
        view->check();
        view->view->WithBridge([&](Bridge &bridge) {
            auto &attached = *found->second;
            auto doc = attached.document.lock();
            if (doc && doc->bridge.lock().get() == &bridge && attached.root) {
                ulbind17::jsc::Traversal walk;
                auto label = copy_to_js(bridge, py::str(name), walk);
                const JSValueRef args[] = {label->value(), attached.root->value()};
                doc->invoke(bridge, "remove", args);
            }
        });
    }
    forget(view.get());
    view->installers.erase(name); view->attachment_cleanup.erase(name);
}
} // namespace binding
