#pragma once
#include "proxy.hpp"
namespace binding::objects {
inline JSValueRef helper_call(const std::weak_ptr<Document> &weak, std::span<const JSValueRef> args) {
    py::gil_scoped_acquire gil;
    auto doc = weak.lock(); auto b = doc ? doc->bridge.lock() : nullptr;
    if (!b || !b->active()) throw Error(Code::PageGone, "Python bridge document expired");
    try {
        auto operation = b->readString(args[0]);
        auto scope = doc->implicit;
        if (b->length(args[1])) {
            auto first = b->at(args[1], 0);
            if (auto node = doc->find(first)) scope = node->session.lock();
        }
        scope->check();
        ulbind17::jsc::Traversal walk;
        auto positional = py::list(from_js(*b, args[1], walk));
        py::object result;
        if (operation == "getattr") {
            if (positional.size() != 2) throw py::type_error("getattr expects an object and a member name");
            auto original = doc->find(b->at(args[1], 0));
            result = policy(doc).attr("_member")(positional[0], positional[1],
                original && original->members ? original->members->object() : py::none());
        } else if (operation == "to_value") {
            if (positional.size() != 1) throw py::type_error("to_value expects one object");
            return copy_to_js(*b, positional[0], walk)->value();
        } else if (operation == "iter") {
            if (positional.size() != 1) throw py::type_error("iter expects one object");
            auto raw = PyObject_GetIter(positional[0].ptr());
            if (!raw) throw py::error_already_set();
            auto iterator = py::reinterpret_steal<py::object>(raw);
            if (scope->closed || !b->active()) return nullptr;
            auto holder = std::make_shared<Ref>(reference(iterator));
            scope->cursors.push_back(holder);
            auto next = b->retain(b->makeFunction([holder, weak_scope = std::weak_ptr<Session>(scope)](JSContextRef, JSObjectRef, std::span<const JSValueRef> args) -> JSValueRef {
                py::gil_scoped_acquire gil;
                auto scope = weak_scope.lock();
                if (!scope) throw Error(Code::PageGone, "Python iterator binding expired");
                scope->check(); auto doc = scope->document.lock(); auto b = doc->bridge.lock();
                try {
                    bool done = !*holder;
                    py::object item = py::none();
                    if (!args.empty() && b->readBoolean(args[0])) { holder->reset(); done = true; }
                    if (!done) {
                        auto iterator = (*holder)->object();
                        auto raw = PyIter_Next(iterator.ptr());
                        if (!raw && PyErr_Occurred()) throw py::error_already_set();
                        if (raw) item = py::reinterpret_steal<py::object>(raw);
                        else { done = true; holder->reset(); }
                    }
                    if (done) std::erase(scope->cursors, holder);
                    if (scope->closed || !b->active()) return nullptr;
                    auto value = b->retain(b->makePlainObject());
                    set_property(*b, value->value(), "done", b->makeBoolean(done));
                    auto converted = scope->convert(*b, item);
                    set_property(*b, value->value(), "value", converted->value());
                    return value->value();
                } catch (py::error_already_set &error) { throw Error(Code::HostException, error.what()); }
    catch (const py::type_error &error) { throw Error(Code::HostException, std::string("TypeError: ") + error.what()); }
            }));
            return next->value();
        } else result = policy(doc).attr("_operate")(operation, positional);
        if (scope->closed || !b->active()) return nullptr;
        return scope->convert(*b, result)->value();
    } catch (py::error_already_set &error) { throw Error(Code::HostException, error.what()); }
    catch (const py::type_error &error) { throw Error(Code::HostException, std::string("TypeError: ") + error.what()); }
}
inline std::shared_ptr<Document> document(Bridge &b) {
    if (auto found = documents.find(&b); found != documents.end()) {
        if (auto value = found->second.lock()) return value;
        documents.erase(found);
    }
    auto doc = std::make_shared<Document>(); doc->bridge = b.shared_from_this();
    doc->policy = reference(py::module_::import("ultralight_py.objects"));
    doc->implicit = doc->session();
    doc->factory = without_gil([&] {
        ulbind17::jsc::String source(factory_source); return b.retain(b.evaluate(source));
    });
    auto helper = b.retain(b.makeFunction([weak = std::weak_ptr<Document>(doc)](JSContextRef, JSObjectRef, std::span<const JSValueRef> args) { return helper_call(weak, args); }));
    const JSValueRef args[] = {helper->value()};
    doc->invoke(b, "install", args);
    // Bridge invalidation clears this rooted closure before dropping the JS
    // context. No Python state is owned by a JSC finalizer or proxy payload.
    auto lifetime = b.makeFunction([doc](JSContextRef ctx, JSObjectRef, std::span<const JSValueRef>) { return JSValueMakeUndefined(ctx); });
    b.protect(lifetime);
    documents[&b] = doc;
    return doc;
}
} // namespace binding::objects
namespace binding {
inline std::optional<py::object> proxy_from_js(Bridge &b, JSValueRef value) {
    auto found = objects::documents.find(&b);
    if (found == objects::documents.end()) return {};
    auto doc = found->second.lock();
    if (!doc) return {};
    auto node = doc->find(value);
    if (!node) return {};
    return node->object->object();
}
inline std::unique_ptr<Bridge::Handle> to_js(Bridge &b, py::handle value, ulbind17::jsc::Traversal &) {
    return objects::document(b)->implicit->convert(b, value);
}
} // namespace binding
