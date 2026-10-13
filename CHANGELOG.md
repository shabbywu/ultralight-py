# 更新日志

## 未发布

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
