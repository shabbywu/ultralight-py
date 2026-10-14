# 原生窗口与 Python API 注册表

`Application` 使用 AppCore 提供系统字体、窗口布局、DPI、系统输入和 IME。
窗口中的页面仍是现有 `View`，资源加载、Session、对象代理和 Promise 桥接共用现有实现。

## 快速开始

```python
import asyncio
from ultralight_py import API, Application

with API("app") as api, Application() as app:

    @api.register
    async def hello(name):
        await asyncio.sleep(0)
        return f"你好，{name}"

    window = app.create_window(800, 520, title="Python 原生窗口")
    api.attach(window.view)
    window.view.load_html("""
        <input placeholder="输入中文">
        <script>
        app.hello('世界').then(value => document.body.append(value));
        </script>
    """)
    app.run()
```

`Application` 必须在首次创建 Runtime 之前创建。`app.runtime` 是现有 Runtime 类型，
后续 `Runtime()` 返回同一个实例。引擎关闭后不能重建。
Application 接受 `assets_root`、`resource_loader`、`cache_path`，参数含义与 Runtime 相同；
`app_name` 和 `developer_name` 默认 `ultralight-py`，供 AppCore 默认存储目录使用。

完整示例使用 Python 虚拟资源、Session、装饰器和异步函数：

```sh
python examples/appcore.py
python examples/appcore.py --smoke
python examples/appcore.py --cpu --smoke
```

## 窗口与 View

`app.create_window(width, height, *, title="", session=None, view=None,
transparent=False, resizable=True, fullscreen=False)` 创建窗口。
尺寸为有限正数，单位是逻辑像素。默认创建一个填满窗口的 View；
显式 Session 必须属于 `app.runtime`。使用已有 View 时传入 `view=...`，
该 View 必须尚未托管且属于应用 Runtime，不能同时指定 Session。
已有 View 保留其渲染及字体配置，Panel 负责后续布局和 DPI 更新。

窗口提供 `view`、`closed`、`width/height`、`device_width/device_height`、
`device_scale` 和可修改的 `title`。`on("resized", callback)` 接收逻辑尺寸元组，
`on("closed", callback)` 接收 None；返回现有 Subscription。回调同步执行，异常转交
Runtime 错误处理器。关闭通知执行前，窗口 View 与相应等待已经关闭。

新建窗口 View 跟随 AppCore 渲染配置；`force_cpu_renderer=True` 使用 CPU 路径。
加速 View 的 `copy_pixels()` 抛 `Unsupported`；`app.runtime.create_view()` 仍创建 CPU 离屏 View。
Window 托管 View 和 Python 包装，丢弃外部 View 引用不会关闭页面。
系统输入由 AppCore 自动转发，焦点经由 Panel；IME 使用 AppCore 的编辑监听器。

## 注册与恢复

`API(namespace)` 使用一个 ASCII JavaScript 标识符作为全局命名空间；`Python`、`ul` 和
`ultralight` 保留。注册项名称也必须是 ASCII JavaScript 标识符。

| 接口 | 行为 |
| --- | --- |
| `register(function, *, name=None)` | 使用函数名或显式名称注册，返回原函数 |
| `@api.register`、`@api.register(name="save")` | 装饰器形式，支持同步和异步可调用对象 |
| `register_object(name, instance, *, members=None)` | 复用现有 Python 对象代理与成员限制 |
| `unregister(name)` | 删除定义，撤销各 View 当前文档中的旧代理；不存在时无操作 |
| `attach(view)` | 加载前附着，或立即安装到当前文档；同一 API 重复附着无操作 |
| `detach(view)` | 立即撤销该 View 的代理并停止导航恢复 |
| `close()`、`closed` | 撤销全部附着，释放注册定义；关闭幂等 |

注册表可以在 Runtime 创建前定义，也可以附着到多个 View。同一 View 不允许两个注册表
使用相同命名空间，已有页面全局名称冲突时附着报错。新增或替换定义立即更新所有附着 View，
旧绑定及其嵌套代理、方法与异步投递被撤销。

内部主框架 `window_ready` 在页面首行脚本之前安装注册表，再通知用户回调。
主框架导航撤销旧文档会话，并按最新定义恢复新文档；用户更换页面回调不会移除重放。
只向主框架注入，附着持续覆盖后续导航；需要停止暴露时显式调用 `detach()`。
每个注册项在每个文档中拥有独立代理会话，其对象、容器和 asyncio 语义见 [对象桥接](objects.md)。
`View.bind_object/bind_function` 仍用于当前文档的临时导出。

View 关闭或最后一次分离 不清空注册定义。API 持有对象直到注销、替换或关闭；
使用 `with API(...)` 可以及时释放这些引用。View 持有附着的原生注册表，注册表弱引用 View。

## 循环和关闭

`app.run()` 在主线程创建 asyncio 循环并持续驱动窗口；已有循环使用
`await app.run_async(update_interval=1/60)`。间隔必须为有限正数。
AppCore 每轮处理系统事件、更新、显示刷新和渲染，同时执行异步投递、条件重检与清理。
没有页面等待时仍持续驱动，页面动画和系统输入继续工作。

`run_once()` 供外部宿主手动步进，返回应用是否仍存活；宿主自行推进 asyncio。
自动运行时禁止另行步进，步进和运行入口均禁止重入。
AppCore Runtime 的 `update/refresh_display/render`、离屏 asyncio 的 `install()` 及
`ScriptDriver.auto()` 抛 `Unsupported`。需要脚本接口时在应用循环中使用
`ScriptDriver(app.runtime)`，它等待应用帧通知，不启动第二个引擎循环。

关闭一个窗口撤销其文档代理、JS Promise 监听、页面等待和桥接投递，
其余窗口继续运行。最后一个窗口关闭后，应用退出并关闭显式 Session、资源加载与 Runtime。
单独关闭 View 或 Session 强制关闭只移除相应 Panel，窗口继续存活。
关闭 Runtime 或 Application 会关闭全部窗口；操作幂等，旧 JS 句柄报 `PageGone`。

`run_async()` 的取消或驱动异常也关闭应用，并传播原异常；调用方 asyncio 循环保持运行。
桥接请求取消自己创建的 Python Task，外部 Task/Future 只解除监听。
取消为协作式请求，任务需正常处理取消。文档引用和延迟 Python 引用在主线程清理，
独立 API 的注册定义仍遵循上述显式关闭规则。

## 平台验收

发行配置包含 Windows x64、Linux x64 和 macOS ARM64 的 AppCore 运行库。
macOS 原生桌面测试覆盖 macOS ARM64 的默认/CPU 渲染、DPI 与像素尺寸、资源加载、
多窗口、Session、异步驱动和关闭路径。Windows/Linux 桌面交互需在对应系统验收。

运行交互示例可验证中文系统字体、窗口拖动与尺寸调整、跨显示器 DPI，
以及中文预编辑、候选框位置、复制粘贴和焦点切换。真实跨屏 DPI 与输入法组合
需要本机交互验证，自动测试不模拟输入法。
