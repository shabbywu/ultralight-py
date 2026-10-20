#pragma once
#include "iteration.hpp"
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
        auto positional = arguments_from_js(*b, args[1]);
        py::object result;
        if (operation == "getattr") {
            if (positional.size() != 2) throw py::type_error("getattr expects an object and a member name");
            auto original = doc->find(b->at(args[1], 0));
            result = policy(doc).attr("member")(positional[0], positional[1],
                original && original->members ? original->members->object() : py::none());
        } else if (operation == "to_value") {
            if (positional.size() != 1) throw py::type_error("to_value expects one object");
            auto value = policy(doc).attr("unwrap")(positional[0]);
            if (py::isinstance<HostValue>(value)) {
                auto original = HostValue::convert(*b, value);
                value = from_js(*b, original->value(), walk, true);
            }
            return copy_to_js(*b, value, walk)->value();
        } else if (operation == "iter") {
            if (positional.size() != 1) throw py::type_error("iter expects one object");
            return make_iterator(scope, *b, positional[0]);
        } else result = policy(doc).attr("operate")(operation, positional);
        if (scope->closed || !b->active()) return nullptr;
        if (py::module_::import("inspect").attr("isawaitable")(result).cast<bool>())
            return async_result(scope, *b, result)->value();
        return scope->convert(*b, result)->value();
    } catch (py::error_already_set &error) { throw Error(Code::HostException, error.what()); }
    catch (const py::type_error &error) { throw Error(Code::HostException, std::string("TypeError: ") + error.what()); }
}
} // namespace binding::objects
