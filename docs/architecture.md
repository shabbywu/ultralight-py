# 架构与维护约定

项目采用三层实现：ulbind17 提供跨语言宿主能力，原生绑定管理 Python/JSC 边界，
Python 层提供公开 API、Python 语义和可选宿主集成。当前范围包含 CPU 离屏渲染和同步、异步双向桥接。

| 层 | 职责与边界 |
| --- | --- |
| `externals/ulbind17` | Renderer/ManagedView、文档失效、通用 Bridge/Handle、输入与资源基础设施 |
| `bindings/` | Python 类型转换、GIL、异常转换、延迟引用释放、Python 对象代理会话 |
| `src/ultralight_py/` | 公开对象封装与校验、成员策略及 Python 运算、输入便利方法 |
| `src/ultralight_py/integrations/` | 可选窗口框架适配；不进入通用 C++ 绑定 |

## Python 依赖

`__init__.py` 和对应 stub 只汇总公开导出。`api.py` 提供 Runtime/Session/View/JSValue；
`input.py` 提供数据与输入 mixin；`objects.py` 提供 PythonBinding。
共享的内部实现通过私有模块导入：`_objects.py` 提供原生代理的成员策略和运算，
`_asyncio.py` 管理循环关联、Promise 等待和延迟投递，`_validation.py` 提供输入校验，
`_support.py` 提供主线程检查和原生调用封装。
`integrations/asyncio.py` 保留公开的 Driver、install 和 run 接口。
`_waiting.py` 管理页面代次、事件分发与被动等待，`events.py` 提供 Subscription；
`scripting.py` 集中合并脚本推进需求，默认借用宿主回调，auto 工厂显式管理按需循环。
Runtime.update 返回原生调用后才重检条件谓词；View 固定内部分发器通过弱引用接入原生回调，
用户替换旧回调槽不会移除内部观察者。Runtime 使用弱集合通知 Python View 关闭和更新。
私有模块中的辅助函数不使用下划线前缀；调用方只导入模块，使用
`_support.call(...)`、`_asyncio.await_result(...)` 等形式访问。
导入统一放在模块顶部并使用绝对路径。相互引用的模块先导入模块对象，
在函数运行时访问类型属性，避免初始化期间读取尚未定义的类型。
三者共用 `_support.py` 的主线程入口与 finally 清理，不让输入或绑定关闭反向依赖 api。
`_objects.unwrap()` 通过 `_api.JSValue` 识别公共句柄；模块初始化时不读取尚未定义的类型。

`api.pyi`、`input.pyi`、`objects.pyi`、`events.pyi`、`scripting.pyi` 分别描述对应模块，根 stub 只重新导出同一类型，
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
| `async.hpp` | Python awaitable 的 JS Promise、会话撤销与 SDK PostTask 投递 |

`conversion.hpp` 保留基础按值转换，循环和深度限制复用 ulbind17 Traversal。
公共 Python bind_function 提供 callable 校验，原生层统一使用 bind_object 绑定。

## 所有权和清理

Runtime 强持有尚未关闭的原生 View 包装，View 弱引用 Runtime。
关闭 View 时从 Runtime 列表移除，局部强引用保护执行中的关闭操作；Runtime 关闭先移出列表再逐一关闭。
Python View 回收仅入队，避免在任意线程直接销毁 SDK 对象。

浏览器存储使用 HostSession，区别于对象桥接的 objects::Session。
Python Runtime 强持有打开的公共 Session，Python View 持有创建时指定的 Session；
原生 Runtime 强持有打开的 HostSession，HostView 强持有 HostSession，HostSession 弱引用 Runtime。
Session 普通关闭以原生 View 列表判断占用，强制关闭只关闭关联 View；释放 SDK Session 引用后移出注册表。
Python 层同步清理已关闭 View 的等待和订阅，原生 View 关闭负责 JS 句柄和异步桥接失效。
Runtime 关闭顺序为 View、显式 Session、Renderer。持久化目录由 SDK 管理，关闭不删除磁盘数据。

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

动态注册入口、JS 工厂回调以及解释器退出钩子即使没有静态调用边，也不能作为 dead code 删除。
内嵌字体、SDK 资源覆盖层与固定版本下载继续复用 ulbind17，未另建通用运行时实现。

## 异步桥接

异步桥接通过 `_asyncio.py` 管理循环关联、任务监听和延迟投递，
原生 `async.hpp` 使用文档及绑定会话限制投递范围，并通过 SDK PostTask 回写。
取消、解绑、导航、关闭及驱动器失败会撤销相关工作；asyncio/Tk 状态留在 Python 宿主层。

页面状态统一保存在 PageState；原始事件继续分发，宿主读取 View 状态判断当前文档，
避免重入导航后旧事件令应用缓存错误地恢复 ready。等待句柄同步登记，再异步等待结果；
ScriptPage.expect_navigation 在动作前登记，共用动作和页面等待的截止时间。
被动等待绑定当前文档，导航上下文绑定已观察到的加载请求；引擎跳转链可继续，
后续显式加载会令其失效。两者都经同一个 ScriptDriver 请求宿主推进。
