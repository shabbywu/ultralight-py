# 原生绑定模块

实现保持 header-only，`module.cpp` 仅负责扩展入口和依次注册 Python API。

- `common.hpp`：共享类型别名、字符串及 GIL 工具。
- `python/`：Python 引用延迟释放、异常转换和基础对象注册。
- `resources/`：Python 资源回调、文件系统和资源类型注册。
- `runtime/`：Runtime 创建、线程检查、错误处理及注册。
- `view/`：View 生命周期、页面事件、加载、像素访问及注册。
- `javascript/`：基础类型转换、保留句柄、属性访问和函数调用及注册。

各目录中的 `bindings.hpp` 提供对应的 `register_*` 入口。
`runtime/views.hpp` 汇集需要 Runtime 和 View 完整类型的所有权与关闭逻辑；
`view/javascript.hpp` 汇集 View 与 JSValue 之间的求值和函数绑定逻辑。
其余头文件通过前置声明避免 Runtime、View、JSValue 相互循环包含。

Python 引用释放仍由 `python/references.hpp` 的延迟队列执行，
线程、GIL、文档失效和回调释放规则与公共 Python API 保持一致。
