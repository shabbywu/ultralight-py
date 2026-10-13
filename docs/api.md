# 公开 API

稳定入口为 `ultralight_py`；`_native`、下划线成员和内部包装构造器不属于公开接口。
通过 Runtime 创建 View，通过 View 或 JSValue 获取 JSValue，通过绑定方法获取 PythonBinding。
原生 Renderer 由 Runtime 管理，不单独暴露 Renderer 类型。

## Runtime

| 接口 | 返回与约定 |
| --- | --- |
| `Runtime(*, assets_root=None, resource_loader=None, cache_path=None)` | 每进程共享的 Runtime；目录接受 str/PathLike，loader 返回 bytes、Resource 或 None |
| `create_view(width, height, *, transparent=False)` | CPU 离屏 View；尺寸为正 uint32，不接受 bool |
| `update()` | 推进页面加载、脚本和清理；不隐式渲染 |
| `refresh_display(display_id=0)` | 通知显示刷新，供动画使用 |
| `render()` | 渲染待更新的离屏页面 |
| `set_error_handler(callback)` | 接收 UltralightError；None 恢复默认 unraisablehook |
| `close()`、`closed` | 幂等关闭全部 View；关闭后不能重新创建 Renderer |

`with Runtime()` 退出即关闭共享实例，因此不要将临时 Runtime 上下文用于一个仍在使用的宿主。
首次配置被冻结，后续省略参数会复用配置；显式传入不同目录或 loader 会报 ValueError。

`cache_path` 指定 Ultralight 的磁盘缓存及浏览器持久化存储根目录，例如
`Runtime(cache_path="./cache")`。显式路径在首次初始化时解析为绝对路径，
不相对于 `assets_root`；接受 str/PathLike，不接受含 NUL 的路径。
`None` 保留 SDK 默认配置；后续传入 `None` 复用首次配置，不会重置目录。
相同目录可以重复指定，不同目录报 ValueError。目录由 SDK 按需创建。
同一 Runtime 的 View 使用默认浏览器 Session，共享存储；该配置不提供账号隔离，
也不代表应用已验证登录仍然有效。

## View

| 接口 | 返回与约定 |
| --- | --- |
| `load_html(html, url="")`、`load_url(url)` | 启动异步加载；html 的 URL 用作相对资源基址 |
| `resize(width, height)` | 调整逻辑像素尺寸，校验同 create_view |
| `set_callbacks(*, begin_loading=None, window_ready=None, dom_ready=None, finish_loading=None, fail_loading=None, console=None, page_settled=None)` | 整组替换旧回调槽；不影响订阅和内部等待 |
| `on(event, callback)` | 返回 Subscription；支持上述七个事件 |
| `is_ready`、`is_settled` | 当前主页面状态；加载开始或失败时清空 |
| `navigation_id`、`load_failure` | 导航代次，以及当前主框架 LoadFailure 或 None |
| `wait_ready(timeout=5)`、`wait_settled(timeout=5)` | 被动异步等待，成功返回 None |
| `wait_until(predicate, timeout=5)` | 被动等待同步谓词，返回首个真值结果 |
| `wait_for_selector(selector, timeout=5)` | 等待主文档中元素存在，返回 True；不判断可见性 |
| `evaluate(source)` | 求值并转换为 Python 值；不负责等待页面加载 |
| `evaluate_handle(source)` | 保留当前文档的 JSValue |
| `bind_object(name, instance, *, members=None)` | 返回 PythonBinding；名称为非空字符串，不能为保留名 Python |
| `bind_function(name, callback)` | callable 专用入口，返回 PythonBinding，保留原 callable 的身份 |
| `unbind(name)` | 撤销该名称绑定；名称不存在时无操作 |
| `copy_pixels()` | 拥有独立 bytes 的 PixelBuffer，读取不清除脏区域 |
| `clear_dirty_bounds()` | 宿主成功消费帧后清除脏区域 |
| `close()`、`closed` | 幂等关闭；上下文退出也关闭 |

对象成员、容器运算和转换规则见 [对象桥接](objects.md)。
输入方法见 [使用指南：输入事件](guide.md#输入事件)，继承的输入 API 同样属于公开 View 接口。
`window_ready` 用于在页面脚本执行前安装绑定；`dom_ready` 用于等待 DOM 可用。
FrameEvent 和 LoadFailure 是独立、只读的事件数据；console 参数为普通字典。
事件可能来自子框架，主页面逻辑应检查 `is_main_frame`。

## 页面等待与事件订阅

所有 View 等待都不调用 `update()`、`refresh_display()` 或 `render()`，也不安装驱动器。
宿主保持完整的帧循环控制权。生命周期等待观察事件；条件等待先检查一次，之后仅在
宿主的 `Runtime.update()` 完成后重检。没有推进时不会持续轮询。

先调用 `load_html/load_url`，再等待当前待加载页面。`wait_ready` 只表示主框架 DOM
已经解析；`wait_settled` 表示 SDK 的网络与布局静默检测已经完成。后者要求宿主持续调用
`update → refresh_display → render`，不保证业务完成或动画永久停止。
新 View 尚未加载时 `is_ready` 为 False，等待仍受超时限制。

`navigation_id` 在 Python 发起加载时立即推进，对应的主框架 begin 不重复计数。
页面自行发起的新主框架 begin 也推进代次；iframe 和 window_ready 不推进。
普通等待绑定开始等待时的文档，替换时抛 `UltralightError(code=PageGone)`。
加载失败抛 `PageLoadError`，其 `failure` 保存原始 LoadFailure；关闭抛 `Closed`。
就绪事件后、等待恢复前发生导航或关闭，也会重新检查有效性。

timeout 必须是正数有限秒数，不接受 bool 或 None。超时抛 `TimeoutError`，取消传播
`asyncio.CancelledError`；仅取消等待，不停止页面加载或 JS 工作。`wait_until` 不接受
异步谓词，谓词自身异常直接传递；选择器语法错误传递为 JavaScriptError。

```python
# 宿主帧循环持续推进 runtime，等待本身不推进。
view.load_url("file:///panel.html")
await view.wait_ready(timeout=5)
await view.wait_for_selector("#status")

with view.on("dom_ready", callback) as subscription:
    ...
```

订阅由 View 保留；丢弃 token 不会取消订阅，需显式 `close()` 或退出上下文。
View/Runtime 关闭会释放订阅及旧回调。内部状态先更新，再调用旧回调和按注册顺序调用
独立订阅。单个回调异常进入 Runtime 错误处理器，其余订阅继续执行。
分发期间新增的订阅从下次事件生效，关闭的订阅立即停止接收。
所有事件回调必须同步；`page_settled` 的参数为 URL 字符串。

## 可选脚本驱动

`ultralight_py.scripting.ScriptDriver` 借用一个 Runtime，`driver.page(view)` 返回借用 View
的 ScriptPage。同一 Runtime 只创建一个 ScriptDriver，供所有页面共享；构造及使用必须在
主线程同一 asyncio 循环中进行。

```python
from ultralight_py.scripting import ScriptDriver

# 独立脚本显式选择库管理的按需循环。
async with ScriptDriver.auto(runtime, update_interval=1 / 60, display_id=0) as driver:
    page = driver.page(view)
    await page.navigate("file:///panel.html", wait_until="settled", timeout=5)
    result = await page.evaluate("getResult()")
    frame = view.copy_pixels()

# 已有宿主调度器：step 只请求宿主推进，执行时机仍由宿主决定。
async with ScriptDriver(runtime, step=host.request_step) as driver:
    await driver.page(view).wait_ready()
```

宿主回调契约为 `async def request_step(*, render: bool = False) -> None`。
返回表示已经完成一次 update 和 refresh_display；render=True 时还须完成 render。
请求可以排队、限频并并入宿主下一帧。适配器不直接调用引擎，多个等待合并为一个在途请求；
后来出现的渲染需求若未进入当前请求，会在下一轮推进时提出。

ScriptPage 提供 View 的四种等待以及 `evaluate(source, timeout=30)`、
`navigate(url, *, wait_until="ready", timeout=30)` 和
`load_html(html, url="", *, wait_until="ready", timeout=30)`；默认超时均为 30 秒。
普通 DOM/条件等待请求 update 和 refresh；settled 以及等待任意 JS Promise 时请求完整帧。
Beta.2 中 requestAnimationFrame Promise 需要 render 才能完成，因此异步求值也提出渲染需求。
立即满足的条件或立即返回的 JS 值不请求推进。
依赖 rAF 或布局的条件/选择器可传 `render=True`；明确只需脚本定时器的
`page.evaluate(..., render=False)` 可关闭求值等待的渲染需求。这些参数只提出需求，
宿主仍决定执行完整帧的时机。

点击、表单提交等动作引起的导航使用上下文，在动作前登记观察器：

```python
async with page.expect_navigation(wait_until="ready", timeout=30):
    page.view.evaluate("setTimeout(() => document.querySelector('a.next').click(), 0)")
await page.wait_for_selector("#result")
```

上下文退出时等待新主页面；旧页面已经 ready 不会提前完成。未发生导航会超时。
动作与等待共用一个单调时钟预算，动作异常或取消会立即释放观察器；异步动作也受超时限制。
超时不能抢占同步 Python/JS。同步 JS 导航可能令求值本身报 PageGone，上例用零延时任务
让求值先返回；上下文不会吞掉动作异常。`navigate` 和 `load_html` 复用同一上下文。

导航操作在动作前登记请求，允许未完成操作中的引擎导航链继续，导航开始后的新 Python 加载调用会
以 PageGone 打断旧操作。SDK 未提供导航原因/请求 ID，因此操作完成前的页面自行跳转也
归入当前链；完成后的跳转不再追踪。导航链共享一个超时预算，不按跳转次数重新计时。

自动模式有等待需求时按间隔推进，没有需求时停止；它与 `integrations.asyncio.install()`
互斥。关闭 ScriptDriver 结束自身操作和推进请求，不关闭借用的 View、Runtime，也不
终止其他被动等待。无驱动器时，自定义宿主仍可完全依靠状态与同步订阅工作。

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

## 图像输出

`PixelBuffer.to_rgba()` 和 `ultralight_py.images.to_rgba(frame)` 返回 `RGBAImage`。
RGBAImage 可从根包或 images 模块导入，构造为 `RGBAImage(width, height, data: bytes)`；
不可变属性为 width、height、data、row_bytes（width * 4）、format（`"RGBA8"`）。
像素为非预乘 RGBA，按行连续且没有填充。它独立于 Runtime/View，转换无需创建 Renderer。
函数入口接受 PixelBuffer 或 RGBAImage，后者直接返回原对象。

| `ultralight_py.images` 接口 | 输出 |
|---|---|
| `to_pillow(frame)` | 独立可修改的 Pillow RGBA Image；需要 `[pillow]` extra |
| `to_numpy(frame, *, copy=True)` | 可写独立的 C 连续 uint8 数组，shape 为 `(height, width, 4)`；需要 `[numpy]` extra |
| `to_numpy(frame, copy=False)` | 转换后 RGBA bytes 的只读视图，保持底层数据存活 |

适配器接受 PixelBuffer 或 RGBAImage，依赖在调用时加载。缺依赖抛带安装提示的 ImportError。
具体 stride、去预乘、校验和所有权规则见 [使用指南：像素](guide.md#像素)。

## 数据与错误

`Resource(data: bytes, mime_type=None, charset="utf-8")` 复制资源数据。
mime_type 省略时存储为空字符串，加载时按文件扩展名推断；不是 Python None。
`PixelBuffer` 是不可变数据类，字段为 width、height、row_bytes、format、dirty_bounds、data。
format 的实际字符串为 `BGRA8Premultiplied`；数据格式和行偏移见 [使用指南：像素](guide.md#像素)。
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
事件与资源异常通过 Runtime 错误处理器报告，规则见 [使用指南：页面事件与异常](guide.md#页面事件与异常)。

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

## Session

`Runtime.create_session(name, *, persistent=False)` creates browser storage shared
by Views in the same Session. `get_session(name)` returns the open object or `None`
without scanning disk. `get_or_create_session(name, *, persistent=False)` reuses
that object; a persistence mismatch raises `ValueError`. Creating an already open
name also raises `ValueError`.

Names must match `[a-z0-9_-]{1,80}`. `default` and Windows device names are reserved.
Invalid names raise `ValueError`; incorrect argument types raise `TypeError`.
`persistent` and `force_close` accept only bool values.

Pass `session=session` to `Runtime.create_view`. `View.session` is read-only and
cannot be switched after creation. Omitting it preserves the default SDK Session
and returns `None` from `View.session`. A closed Session raises `Closed` when used
for a new View; a Session owned by another Runtime raises `CrossContext`.

Session exposes read-only `name`, `persistent`, `disk_path`, and `closed` properties.
`disk_path` is an absolute `Path` reported by the SDK, or `None` for temporary
storage. Persistent Sessions use named subdirectories of `Runtime(cache_path=...)`.
Cookies with an explicit expiry, localStorage and IndexedDB survive normal process
shutdown. The SDK has no explicit flush API. Session storage is isolated across
Sessions, while sessionStorage remains independent per View.

Runtime retains open Sessions and Views retain their Session. Closing all Views
leaves their Session available for new Views. `session.close()` raises `Busy` while
associated Views remain open. `session.close(force_close=True)` closes those Views,
including page waits, subscriptions, JS handles and asynchronous bridges. Other
Sessions' Views remain open. Closing is idempotent; metadata remains readable.
Closing never deletes persistent data. Recreating a temporary Session with the
same name starts empty; persistent Sessions reuse their disk directory.

Session supports context management; exit calls ordinary `close()`, so Views must
be closed first. Runtime shutdown closes Views, then explicit Sessions, then the
Renderer. Session operations follow the same main-thread and resource-callback
restrictions as Runtime and View. `force_close` only bypasses the View occupancy
check. Browser storage isolation does not isolate Python code or host resources.

See [the multi-Session example](../examples/sessions.py). Account configuration,
login validity, task assignment, disk deletion, data import/export and concurrent
cross-process access remain the application's responsibility.
