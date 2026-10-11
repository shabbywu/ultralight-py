# 公开 API

稳定入口为 `ultralight_py`；`_native`、下划线成员和内部包装构造器不属于公开接口。
通过 Runtime 创建 View，通过 View 或 JSValue 获取 JSValue，通过绑定方法获取 PythonBinding。
原生 Renderer 由 Runtime 管理，不单独暴露 Renderer 类型。

## Runtime

| 接口 | 返回与约定 |
| --- | --- |
| `Runtime(*, assets_root=None, resource_loader=None)` | 每进程共享的 Runtime；目录接受 str/PathLike，loader 返回 bytes、Resource 或 None |
| `create_view(width, height, *, transparent=False)` | CPU 离屏 View；尺寸为正 uint32，不接受 bool |
| `update()` | 推进页面加载、脚本和清理；不隐式渲染 |
| `refresh_display(display_id=0)` | 通知显示刷新，供动画使用 |
| `render()` | 渲染待更新的离屏页面 |
| `set_error_handler(callback)` | 接收 UltralightError；None 恢复默认 unraisablehook |
| `close()`、`closed` | 幂等关闭全部 View；关闭后不能重新创建 Renderer |

`with Runtime()` 退出即关闭共享实例，因此不要将临时 Runtime 上下文用于一个仍在使用的宿主。
首次配置被冻结，后续省略参数会复用配置；显式传入不同目录或 loader 会报 ValueError。

## View

| 接口 | 返回与约定 |
| --- | --- |
| `load_html(html, url="")`、`load_url(url)` | 启动异步加载；html 的 URL 用作相对资源基址 |
| `resize(width, height)` | 调整逻辑像素尺寸，校验同 create_view |
| `set_callbacks(*, begin_loading=None, window_ready=None, dom_ready=None, finish_loading=None, fail_loading=None, console=None)` | 整组替换；省略或 None 清空对应回调 |
| `evaluate(source)` | 求值并转换为 Python 值；不负责等待页面加载 |
| `evaluate_handle(source)` | 保留当前文档的 JSValue |
| `bind_object(name, instance, *, members=None)` | 返回 PythonBinding；名称为非空字符串，不能为保留名 Python |
| `bind_function(name, callback)` | callable 专用入口，返回 PythonBinding，保留原 callable 的身份 |
| `unbind(name)` | 撤销该名称绑定；名称不存在时无操作 |
| `copy_pixels()` | 拥有独立 bytes 的 PixelBuffer，读取不清除脏区域 |
| `clear_dirty_bounds()` | 宿主成功消费帧后清除脏区域 |
| `close()`、`closed` | 幂等关闭；上下文退出也关闭 |

对象成员、容器运算和转换规则见 [对象桥接](objects.md)。
输入方法见 [README 输入事件](../README.md#输入事件)，继承的输入 API 同样属于公开 View 接口。
`window_ready` 用于在页面脚本执行前安装绑定；`dom_ready` 用于等待 DOM 可用。
FrameEvent 和 LoadFailure 是独立、只读的事件数据；console 参数为普通字典。
事件可能来自子框架，主页面逻辑应检查 `is_main_frame`。

## JSValue 与 PythonBinding

| 接口 | 返回与约定 |
| --- | --- |
| `JSValue.get(key)` | 属性值句柄；key 为 str/int，不接受 bool |
| `JSValue.set(key, value)` | 设置属性；基础值、Python 实时代理、同文档 JSValue 均可传入 |
| `JSValue.keys()` | 自有可枚举字符串属性名 list，不读取属性值 |
| `JSValue.call(*args, this=None)` | 结果句柄；this 可传同文档 JSValue，保留 JS 方法 receiver |
| `JSValue.to_python()` | 基础值及普通 JS 容器按值转换；Python 代理恢复原对象 |
| `JSValue.close()`、`closed` | closed 表示显式关闭，不能用于判断导航失效 |
| `PythonBinding.close()`、`closed` | 撤销该绑定导出的全部代理；导航/关闭也会令 closed 为 true |

两种句柄均支持 `with`。丢弃 PythonBinding 不自动解绑；丢弃 JSValue 会释放保留句柄，
释放可能延迟到主线程调用。没有通用 `valid` 属性；操作时检查文档有效性。
同一 Python callable 用 bind_function/bind_object 导出后，回传时恢复原 callable。
不同显式绑定仍拥有独立的代理身份和撤销范围。

## 数据与错误

`Resource(data: bytes, mime_type=None, charset="utf-8")` 复制资源数据。
mime_type 省略时存储为空字符串，加载时按文件扩展名推断；不是 Python None。
`PixelBuffer` 是不可变数据类，字段为 width、height、row_bytes、format、dirty_bounds、data。
format 的实际字符串为 `BGRA8Premultiplied`；数据格式和行偏移见 [README 像素](../README.md#像素)。
`undefined` 是单例；判断 JS undefined 使用 `value is undefined`，与 None/null 区分。

UltralightError 继承 RuntimeError，JavaScriptError 继承 UltralightError。
诊断字段为 code、stack、source_url、line、column；位置缺失时由原生诊断默认值表示。
ErrorCode 是原生枚举，支持名称属性 `.name`、数值 `.value` 和 `int(code)`，
不承诺 Python Enum 的遍历协议。常见错误如下：

| code | 常见原因 |
| --- | --- |
| WrongThread | 在非 Python 主线程操作引擎或显式关闭句柄 |
| Closed | Runtime 或 View 已关闭 |
| PageGone | JS 句柄所属文档失效，或 Python 绑定已撤销 |
| CrossContext | 把 JSValue 传给另一 View/文档 |
| Busy | 重入 Renderer、输入，或在资源回调中操作引擎 |
| ScriptException | JS 执行失败，对应 JavaScriptError |
| TraversalLimit | 普通 JS 容器或按值复制存在循环/超过深度限制 |

Python 参数校验还可能直接抛 TypeError、ValueError、OverflowError。
Python 桥接异常进入页面后为 JS Error；页面捕获后可以继续运行。
事件与资源异常通过 Runtime 错误处理器报告，规则见 [README 页面事件与异常](../README.md#页面事件与异常)。

## 线程与可选集成

引擎操作和显式 close 在 Python 主线程进行，宿主负责驱动循环。
closed 是状态查询，不会启动引擎操作；PythonBinding.closed 可从其他线程查询撤销状态。
资源 loader 可能在后台线程执行，不能操作 Runtime/View/JS，也不能等待主线程推进加载。
输入回调、Renderer 回调和 JS 桥接中的再次输入应排队到宿主下一轮。

`ultralight_py.integrations.tkinter.TkInputAdapter(widget, view, *, coordinate_transform=None, wheel_pixels=40)`
只管理输入适配。close 解除自身绑定，释放借用引用，不关闭 View、Runtime 或控件。
渲染、帧转换和定时驱动由宿主承担；普通包导入不依赖 tkinter 或 Pillow。
事件回调为同步接口；Promise/asyncio 桥接见下节。

## Promise 与 asyncio

`await JSValue.await_result()` 等待 JS Promise，返回需要关闭的 `JSValue`。
非 Promise 抛出 `TypeError`；rejection 抛出带错误信息的 `JavaScriptError`。
`await View.evaluate_async(source)` 求值并返回 Python 值，普通结果直接转换。
`await JSValue.call_async(*args, this=None)` 返回 `JSValue`，普通结果也保持为句柄。
导航或关闭使等待以 `UltralightError(code=ErrorCode.PageGone)` 结束。
取消 Python 等待只解除桥接监听，JS Promise 本身继续执行。

绑定函数和对象方法返回 awaitable 时，JS 获得 Promise。asyncio 调度 Python
任务；完成值在后续 `Runtime.update()` 中送入 JS。异常使 Promise rejected。
解绑、替换绑定、导航和关闭立即撤销投递，并请求取消桥接创建的 Task。
传入的外部 Task/Future 只解除监听，不会被桥接取消。取消是协作式请求。

```python
from ultralight_py.integrations.asyncio import run, install

run(main(), runtime=runtime, update_interval=1 / 60)

# 已有运行中的 asyncio 循环：
driver = install(runtime, update_interval=1 / 60)
try:
    result = await view.evaluate_async("Promise.resolve(42)")
finally:
    driver.close()
```

await 不隐式 update。自定义宿主可以自行调用 update，不必安装驱动器。
首次异步操作关联当前循环；同一 Runtime 同时只允许一个循环和一个驱动器。
引擎操作必须在主线程执行。驱动器只 update，不渲染，也不关闭传入的 Runtime。
更新间隔是目标调度间隔；阻塞宿主线程或长时间执行 JS 会延迟更新。
驱动器关闭或失败会终止关联的跨语言等待和投递；`run()` 传播驱动错误，
退出时清理定时器、监听和任务。关闭驱动器后的 JS Promise 可能保持 pending。
当前不提供 Tk/asyncio 联合循环或 JS AbortSignal。
