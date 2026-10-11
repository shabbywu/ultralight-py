#pragma once
#include "common.hpp"
#include "../javascript/conversion.hpp"
namespace binding {
inline ultralight::String input_string(py::handle value) {
    auto text = unicode(value);
    return ultralight::String(reinterpret_cast<const ultralight::Char16 *>(text.data()), text.size());
}
inline void key_event(HostView &host, int type, unsigned modifiers, int key, int native,
                      py::object identifier, py::str text, py::str unmodified,
                      bool keypad, bool repeat, bool system) {
    if (type < 0 || type > 3 || (modifiers & ~15u)) throw py::value_error("Invalid key event type or modifiers");
    ultralight::KeyEvent event;
    event.type = static_cast<ultralight::KeyEvent::Type>(type);
    event.modifiers = modifiers; event.virtual_key_code = key; event.native_key_code = native;
    if (identifier.is_none()) ultralight::GetKeyIdentifierFromVirtualKeyCode(key, event.key_identifier);
    else event.key_identifier = input_string(identifier);
    event.text = input_string(text); event.unmodified_text = input_string(unmodified);
    event.is_keypad = keypad; event.is_auto_repeat = repeat; event.is_system_key = system;
    event.platform_event = nullptr;
    with_input(host, [&](auto &view) { view.FireKeyEvent(event); });
}
} // namespace binding
