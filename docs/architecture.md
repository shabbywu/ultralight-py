# 架构与维护约定

项目采用三层实现：ulbind17 提供跨语言宿主能力，原生绑定管理 Python/JSC 边界，
Python 层提供公开 API、Python 语义和可选宿主集成。现有分层适合当前 CPU 离屏与同步桥接范围。

| 层 | 职责与边界 |
| --- | --- |
| `externals/ulbind17` | Renderer/ManagedView、文档失效、通用 Bridge/Handle、输入与资源基础设施 |
| `bindings/` | Python 类型转换、GIL、异常转换、延迟引用释放、Python 对象代理会话 |
| `src/ultralight_py/` | 公开对象封装与校验、成员策略及 Python 运算、输入便利方法 |
| `src/ultralight_py/integrations/` | 可选窗口框架适配；不进入通用 C++ 绑定 |

## Python 依赖

`__init__.py` 和对应 stub 只汇总公开导出。`api.py` 提供 Runtime/View/JSValue；
`input.py` 提供数据与输入 mixin；`objects.py` 提供 PythonBinding 和原生代理调用的 Python 策略。
三者共用 `_support.py` 的主线程入口与 finally 清理，不让输入或绑定关闭反向依赖 api。
`objects._unwrap()` 为识别公共 JSValue 延迟导入其类型；这是运行时转换的依赖，不参与模块初始化。

`api.pyi`、`input.pyi`、`objects.pyi` 分别描述对应模块，根 stub 只重新导出同一类型，
避免根入口与模块入口出现两个不同的静态类型。Tk 适配器拥有独立 stub。
公开 callable 直接交给对象绑定，不再通过临时 Python 函数包装其身份。

## 原生模块

保持 header-only，`module.cpp` 只负责注册顺序。模块按职责组织目录，不拆出多份 cpp。
Runtime/View 互相引用时使用前置声明，需完整类型的所有权操作汇集在 `runtime/views.hpp`。
View/JSValue 的交叉操作位于 `view/javascript.hpp`。

对象桥接目录划分如下：

| 头文件 | 职责 |
| --- | --- |
| `state.hpp` | Document、Session、Node 的持有关系、查找与撤销 |
| `factory.hpp` | JS Proxy 工厂及保留的 Python 命名空间 |
| `proxy.hpp` | 成员回调、callable 调用与会话内身份转换 |
| `iteration.hpp` | Python 迭代器适配及完成/提前退出后的引用释放 |
| `operators.hpp` | JS Python 运算入口、绑定范围选择与异常转换 |
| `document.hpp` | 文档初始化、生命周期守卫与通用转换入口接线 |

`conversion.hpp` 保留基础按值转换，循环和深度限制复用 ulbind17 Traversal。
实时代理转换不再携带无用的 Traversal 参数。删除了原生层中仅转调 bind_object 的 bind_function；
公共 Python bind_function 继续提供 callable 校验与绑定入口。

## 所有权和清理

Runtime 强持有尚未关闭的原生 View 包装，View 弱引用 Runtime。
关闭 View 时从 Runtime 列表移除，局部强引用保护执行中的关闭操作；Runtime 关闭先移出列表再逐一关闭。
旧实现等到 update 才扫描清理，现改为即时移除，更新入口不再重复扫描。
Python View 回收仅入队，避免在任意线程直接销毁 SDK 对象。

每个有效文档通过 Bridge 的生命周期守卫持有 Document。
Document 强持有隐式会话及命名会话，Session 持有 Node 和迭代器引用；反向关联均为弱引用。
JS payload 不持有 Python 强引用，文档失效清除守卫，先撤销会话再释放对象。
文档注册表只保存弱引用，Document 销毁时删除对应记录，防止长期导航积累过期条目。
注册表访问与守卫撤销都在文档所属线程进行；其他线程只可查询原子绑定关闭状态。

所有 Python 强引用封装在 PythonRef 中。析构只向队列提交 PyObject，
主线程持有 GIL 时 drain；JSC GC/finalizer 中不获取 GIL。
会话按对象身份保留代理直到撤销或文档失效，不依赖 JS GC 推断 Python 对象是否还可被访问。
没有被消费完或提前 return 的迭代器也保留到会话失效。
Python 回调若捕获 View/Runtime，可形成跨语言引用环，应用应显式 close。

## 本轮审查结论

消除了等待 update 才释放已关闭 View 包装的延迟及过期文档注册记录的积累，
移除了重复 callable 包装、重复解包及原生转调入口，
提取共用调用工具，并按会话、代理、运算、迭代、初始化进一步拆分头文件。
动态注册入口、JS 工厂回调以及解释器退出钩子即使没有静态调用边，也不能作为 dead code 删除。
内嵌字体、SDK 资源覆盖层与固定版本下载继续复用 ulbind17，未另建通用运行时实现。

未来加入异步桥接时，需要单独定义任务取消、导航失效和事件循环驱动；
不应将 asyncio/Tk 状态写入通用 Bridge。跨平台与更多 Python 版本仍需实际验收，见发布说明。
