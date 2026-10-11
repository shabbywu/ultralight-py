#pragma once
#include "../common.hpp"
#include <deque>
#include <mutex>
namespace binding {
// JSC may destroy closures on a collector thread. Never acquire the GIL in a
// collector/finalizer: the Python thread may itself be waiting for that thread.
struct Cleanup {
    std::mutex mutex;
    std::deque<PyObject *> references;
    std::deque<std::function<void()>> tasks;
};
inline Cleanup &cleanup() { static auto *value = new Cleanup; return *value; }
struct PythonRef {
    PyObject *value;
    explicit PythonRef(py::handle object) : value(object.ptr()) { Py_INCREF(value); }
    ~PythonRef() {
        auto &queue = cleanup();
        std::lock_guard lock(queue.mutex);
        queue.references.push_back(value);
    }
    py::object object() const { return py::reinterpret_borrow<py::object>(value); }
};
using Ref = std::shared_ptr<PythonRef>;
inline Ref reference(py::handle value) { return std::make_shared<PythonRef>(value); }
inline void drain() {
    auto &queue = cleanup();
    for (;;) {
        std::deque<PyObject *> references;
        std::deque<std::function<void()>> tasks;
        {
            std::lock_guard lock(queue.mutex);
            references.swap(queue.references); tasks.swap(queue.tasks);
        }
        if (references.empty() && tasks.empty()) break;
        for (auto &task : tasks) task();
        for (auto *value : references) Py_DECREF(value);
    }
}
} // namespace binding
