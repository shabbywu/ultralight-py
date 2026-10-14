# 更新日志

## 0.5.0（待发布）

- Windows wheel 修复时排除由系统加载器解析的 `ext-ms-win-*` API set，避免分析 AppCore DLL 依赖时因找不到对应文件而失败。
- 将 API 和 AppCore 按职责拆分为公开子模块，支持 `api.runtime`、`api.view`、`api.values`、`appcore.application` 和 `appcore.window` 导入。
- 错误、资源和页面事件类型统一由 `ultralight_py` 根入口导出；进程退出清理在首次创建 Runtime 或 Application 时注册。

- 新增 AppCore Application/Window：系统字体、DPI、原生输入与 IME，复用 Runtime、View、资源加载和 Session。
- 新增独立 API 注册表与 `@api.register`，支持对象代理、加载前附着、导航恢复及即时更新与撤销。
- 提供同步/asyncio 应用循环和手动步进；统一窗口关闭、页面等待、异步投递与 Python 引用清理，wheel 包含 AppCore。

- 新增原生 Session API：创建、查询、复用、持久化和关闭；View 可指定 Session，支持关联 View 占用检查和强制关闭。

- 增加独立 RGBAImage 与原生 BGRA/stride/去预乘转换；提供延迟加载的可选 Pillow/NumPy 输出，转换可在线程池中执行。

- 增加多订阅事件与主框架页面状态；旧回调槽替换不影响内部等待和独立订阅。
- 提供被动 `wait_ready/wait_settled/wait_until/wait_for_selector`、结构化 PageLoadError，处理导航、关闭、超时和取消。
- 增加可选 ScriptDriver：宿主注入推进回调，或显式启用共享的按需循环；脚本导航跟随未完成的引擎导航链。
- 增加 `ScriptPage.expect_navigation`，在点击/提交前登记等待；动作与新页面就绪共用超时预算。
- Runtime 支持 `cache_path`，配置磁盘缓存及浏览器持久化存储目录，遵循首次初始化冻结规则。
- 支持 Python 实例和容器实时代理、绑定隔离及撤销。
- 提供 `Python.to_value()`，将 Python 容器复制为普通 JS Array／Object。
- 支持 JS Promise 等待、异步求值和调用，以及 Python awaitable 转 JS Promise。
- 提供 asyncio 定时驱动入口；await 不隐式调用 `Runtime.update()`。
- 取消、解绑、导航、关闭及驱动器失败时清理相关等待和投递。
