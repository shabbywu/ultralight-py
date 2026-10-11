# 更新日志

## 未发布

- 支持 Python 实例和容器实时代理、绑定隔离及撤销。
- 提供 `Python.to_value()`，将 Python 容器复制为普通 JS Array／Object。
- 支持 JS Promise 等待、异步求值和调用，以及 Python awaitable 转 JS Promise。
- 提供 asyncio 定时驱动入口；await 不隐式调用 `Runtime.update()`。
- 取消、解绑、导航、关闭及驱动器失败时清理相关等待和投递。
