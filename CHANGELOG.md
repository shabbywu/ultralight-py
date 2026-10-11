# 发布说明

## 0.2.0（本地验收，尚未发布）

Python 创建的实例可直接供 JS 访问公开属性、property 和方法。
同类实例拥有独立状态与绑定方法；每个显式绑定拥有独立代理身份和撤销范围。

- 新增 `View.bind_object()`、`View.unbind()` 与可关闭的 PythonBinding。
- list/dict/tuple 使用实时代理，支持 Python 方法、严格索引、切片、迭代和关键字调用。
- `bind_function()` 返回 PythonBinding，并保留原 callable 的身份。
- 保留 CPU 离屏渲染、页面事件、JSValue、虚拟资源、输入事件和可选 Tk 输入适配。
- 收敛公开 API 与模块类型声明，补齐 Tk stub，修正 ErrorCode 的原生枚举声明。
- 关闭 View 后移除 Runtime 所有权；文档失效后删除注册记录，避免包装与过期记录积累。

### 兼容性变化

Python 容器作为函数返回值或 JSValue 参数时不再自动复制为 JS Array/Object。
需要普通 JS 数据时调用 `Python.to_value()`；实时代理回传 Python 恢复原对象。
JS 有限安全整数转为 Python int，其余数字为 float，保留负零。
完整迁移示例见 [对象桥接与迁移说明](docs/objects.md)。

### 平台与验证边界

| 环境 | 状态 |
| --- | --- |
| macOS ARM64，普通 GIL Python 3.13.16，Ultralight 2.0.0-beta.2 | 本地发行包与功能验收；Tk 8.6 Aqua 实际窗口 |
| Python 3.10–3.12、3.14+ | 包声明 Python 3.10+，尚未逐版本完成当前 0.2.0 验收 |
| Linux x64、Windows x64 | 依赖提供构建支持，Python 绑定尚未实测 |
| Tk Win32/X11 | 模拟输入映射验证，尚未对应平台真实窗口验收 |
| Free-threaded Python、子解释器 | 尚未验证，不声明支持 |

本地验证从 sdist 构建 wheel、安装后运行生命周期/对象隔离等测试及离屏、桥接、资源、对象和 Tk 示例。
未建立 CI/CD，也未上传发行包。

### 当前边界

Renderer 每进程唯一，关闭后不能重建。引擎操作限定 Python 主线程，宿主负责更新与渲染循环。
Python 对象在绑定或文档失效时释放，不保证 JS GC 及时释放。
尚无 JS 类构造器、Promise/asyncio、GPU View、零复制像素或输入法预编辑。
成员白名单只限制根对象，不递归限制整个对象图。
