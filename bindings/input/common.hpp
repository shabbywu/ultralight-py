#pragma once
#include "../view/view.hpp"
namespace binding {
// Copy the managed wrapper before dispatch: a Python callback may clear host.view.
template <typename F> decltype(auto) with_input(HostView &host, F &&callback) {
    host.check();
    auto view = *host.view;
    return without_gil([&]() -> decltype(auto) { return callback(view); });
}
} // namespace binding
