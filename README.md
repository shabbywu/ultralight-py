# ultralight-py

Ultralight 2.x 的 Python 绑定，支持 CPU 离屏渲染、页面事件、Python/JavaScript
双向函数调用、Python 实例与容器实时代理、文档级 JS 句柄、Python 虚拟资源加载，
以及鼠标、滚动和键盘输入。

文档：[公开 API](docs/api.md) · [对象桥接与迁移](docs/objects.md) ·
[架构与维护约定](docs/architecture.md) · [0.3.0 发布说明](CHANGELOG.md)。

依赖通过 `externals/pybind11` 和 `externals/ulbind17` 子模块管理。
需要 Python 3.10+、CMake 3.22+ 和支持 C++20 的编译器。

```sh
git submodule update --init --recursive
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
python -c "import ultralight_py"
```

默认下载 Ultralight 2.0.0-beta.2 SDK，也可指定本地 SDK：

```sh
python -m pip install -e . -Ccmake.define.ULTRALIGHT_SDK_ROOT=/absolute/path/to/sdk
```

当前实际验收环境为 macOS ARM64、普通 GIL Python 3.13.16。包要求 Python 3.10+，
其他 Python 版本尚未逐版本完成当前 0.3.0 验收；
Linux x64、Windows x64 保留依赖的构建支持，尚未完成 Python 绑定实测验收。
pybind11 固定 v3.0.4，ulbind17 固定 `670910c`，默认 SDK 固定 2.0.0-beta.2。

## 最小离屏闭环

```python
import time
from ultralight_py import Runtime

with Runtime() as runtime:
    with runtime.create_view(320, 180) as view:
        ready = []
        view.set_callbacks(
            dom_ready=lambda event: ready.append(event) if event.is_main_frame else None,
        )
        view.load_html('<style>body{background:#ff0000}</style><body>Hello')
        deadline = time.monotonic() + 5
        while not ready:
            if time.monotonic() >= deadline:
                raise TimeoutError("Page did not become ready")
            runtime.update()
            runtime.refresh_display()
            runtime.render()
            time.sleep(0.005)
        print(view.evaluate("document.body.textContent"))
        frame = view.copy_pixels()
        print(frame.width, frame.height, frame.row_bytes, frame.format)
        view.clear_dirty_bounds()
```

完整示例包含加载错误处理：

```sh
python examples/offscreen.py
python examples/bridge.py
python examples/resources.py
python examples/objects.py
python -m pytest tests -q
```

## 运行时、线程与释放

- `Runtime()` 返回每进程唯一实例，重复调用共享 Renderer。首次调用冻结资源配置；
  后续传入不同的目录或 loader 会报错。`Runtime.close()` 关闭全部 View，关闭后不能重建
  Renderer；日常复用 Runtime，反复创建和关闭 View。上下文管理器退出会执行关闭。
- Runtime、View、JSValue 的操作和显式关闭只能在 Python 主线程进行。运行时不启动宿主循环；
  必须自行调用 `update()`、`refresh_display()` 和 `render()`。`update()` 也推进句柄及回调清理。
- View 的垃圾回收只将关闭任务入队，在后续主线程调用中处理。使用 `close()` 或 `with`
  获得及时释放；`atexit` 会在解释器退出前关闭 Runtime。回调捕获 View/Runtime 时可能形成
  Python 与原生对象之间的引用环，显式关闭会解除回调引用。
- JSValue 保留当前文档中的值；主框架导航或关闭 View 后旧句柄报 `PageGone`，
  不能传入其他 View/文档。`JSValue.closed` 只表示该句柄已被显式关闭，不能用它判断导航失效。
- 更新或渲染回调中允许关闭 View、导航和替换回调，不能嵌套驱动 Renderer。
  JS 执行中的导航/关闭可能使当前求值报 `PageGone`。

## 页面事件与异常

`view.set_callbacks(...)` 整组替换回调，省略的回调清空。支持：

| 回调 | 参数 |
| --- | --- |
| `begin_loading`、`window_ready`、`dom_ready`、`finish_loading` | `FrameEvent(frame_id, is_main_frame, url)` 的只读属性 |
| `fail_loading` | `LoadFailure`：`frame`、`description`、`domain`、`code` |
| `console` | 字典：`message`、`source`、`type`、`level`、`source_url`、`line`、`column` |

事件数据拥有独立寿命，不引用 SDK 回调期间的借用对象。事件可能包含子框架，应检查
`is_main_frame`。加载完成不保证加载成功，需要单独处理 `fail_loading`。
无脚本页面可能不触发 `window_ready`；依赖 DOM 时使用 `dom_ready`。

同步引擎错误抛 `UltralightError`，脚本错误抛其子类 `JavaScriptError`。
原生诊断提供 `code`、`stack`、`source_url`、`line` 和 `column`。
Python 参数类型错误使用 `TypeError`/`ValueError`，整数超范围使用 `OverflowError`。

Python 函数、实例方法及属性访问的异常转为页面中的 JS Error。页面事件和资源 loader 的异常被隔离，
交给 `runtime.set_error_handler(callback)`；资源错误在后续 `update()` 或关闭时派发。
默认通过 `sys.unraisablehook` 报告，传入 `None` 可恢复默认处理。
错误处理器自身的异常也通过该 hook 报告，不会跨 SDK 边界抛出。

## Python 与 JavaScript

```python
def window_ready(event):
    if event.is_main_frame:
        view.bind_function("python_add", lambda a, b: a + b)

view.set_callbacks(window_ready=window_ready)
view.load_html('<script>window.answer=python_add(20,22)</script>')
# 驱动 update()，等待主框架 DOM 就绪后：
assert view.evaluate("answer") == 42

with view.evaluate_handle("({offset:10, add(n){return this.offset+n}})") as obj:
    obj.set("offset", 20)
    with obj.get("add") as fn:
        with fn.call(2, this=obj) as result:
            assert result.to_python() == 22
```

函数只绑定当前文档，不自动跨导航重放。在每次主框架 `window_ready` 中显式重绑；
向页面注册函数意味着允许该页面调用 Python，请由应用选择注册的文档。

`evaluate()` 返回 Python 值；`evaluate_handle()` 返回 JSValue。句柄支持
`get(str_or_int)`、`set(key, value)`、`keys()`、`call(*args, this=None)` 和 `to_python()`。
`get()` 和 `call()` 返回句柄，显式指定 `this` 可保留方法的 receiver。
`set()`/`call()` 的单个值以及 Python callable 的返回值可以是同文档 JSValue。
实时 Python 容器中的 JSValue 也会在访问时检查所属文档；显式按值复制不转换 JSValue。

| Python | JavaScript |
| --- | --- |
| `None` | null |
| `ultralight_py.undefined` | undefined |
| bool | Boolean |
| int、float | Number；JS 安全整数返回 int，其余返回 float |
| str | String，保留 Unicode 和内嵌 NUL |
| list、tuple | 实时 Python 代理；普通 JS Array 回传时复制为 list |
| dict | 实时 Python 映射代理，保留 Python 键类型 |
| 普通实例、callable | 属性/方法代理或可调用代理；回传时恢复原对象 |

Python int 必须位于 ±(2⁵³−1)，不进行隐式字符串/数字转换。JS 数组与普通对象递归转换为
list/dict；函数、Promise、Date 等原生 JS 特殊对象通过 JSValue 使用。普通 JS 容器的循环引用或超过
64 层的转换报 `TraversalLimit`，按值转换不保留对象别名。Python 代理支持循环引用，
回传 Python 时恢复原对象。
对象转换会读取自有可枚举字符串属性，可能执行 getter；`keys()` 不读取属性值。

## Python 对象与实时容器

```python
class Counter:
    def __init__(self, value):
        self.value = value
        self.history = []

    def increment(self):
        self.value += 1
        self.history.append(self.value)
        return self.value

left, right = Counter(0), Counter(100)
left_binding = view.bind_object("left", left)
right_binding = view.bind_object("right", right)
view.evaluate("left.increment(); right.increment()")
assert (left.value, right.value) == (1, 101)
assert view.evaluate("left.history") is left.history
left_binding.close()
```

自动暴露公开属性、property 和方法；可通过 `members=[...]` 收窄根对象成员。
同类实例的方法与状态分别管理，每个绑定内部保持对象身份，解除绑定使已导出的嵌套代理和方法失效。
主框架导航后重新绑定；View 持有 PythonBinding，丢弃句柄不会解除绑定。

**0.2.0 有转换行为变更**：Python list/dict/tuple 统一使用实时代理，
包括函数返回值和 JSValue 的参数。JS 使用 Python 的 `append`、`get` 等方法，
严格索引使用 `Python.getitem/setitem/delitem`，不模拟 JS Array/Object。
需要普通 JS 数据时使用 `Python.to_value()` 显式复制。
完整 API、身份和释放规则见 [对象桥接与迁移说明](docs/objects.md)。

## 资源加载

```python
from ultralight_py import Resource, Runtime

files = {
    "page.html": Resource(b'<script src="app.js"></script>', "text/html"),
    "app.js": b"window.answer=42",
}
runtime = Runtime(assets_root="./assets", resource_loader=files.get)
view = runtime.create_view(320, 180)
view.load_url("file:///page.html")
```

加载顺序为内嵌 ICU/证书、Python loader、本地文件系统。SDK 资源不交给 Python loader。
`assets_root=None` 使用首次初始化时的工作目录，显式目录解析为绝对路径。
`load_html(html, url="")` 的 URL 可为相对资源提供页面基址；`load_url()` 也支持 HTTP/HTTPS URL。
默认字体来自 ulbind17 内嵌字体，不自动发现系统字体。

`resource_loader(path)` 返回 `bytes`、`Resource(data, mime_type=None, charset="utf-8")`
或 `None`。只有 `None` 触发本地目录回退；异常或错误返回类型导致该资源读取失败。
未指定 MIME 时按扩展名推断，编码默认 UTF-8；SDK Buffer 拥有内容副本，包括空 bytes。

SDK 可从主线程和后台加载线程重复调用 loader。结果不缓存，回调应在同一次加载中返回一致内容，
共享状态需要自行同步。loader 内禁止操作 Runtime/View/JS，也不要等待主线程驱动页面。
关闭会停止新 loader 调用，释放 GIL 等待正在执行的回调结束，再清除 Python 引用。

## 像素

`copy_pixels()` 返回拥有独立 bytes 的不可变 PixelBuffer，View 关闭后仍可使用。
包含 `width`、`height`、`row_bytes`、`format`、`dirty_bounds` 和 `data`。
格式固定为 **BGRA8、预乘 alpha**，行可能有填充；像素 `(x,y)` 的偏移为
`y * row_bytes + x * 4`。`dirty_bounds` 为 `(left, top, right, bottom)`，右/下边界不包含在内。
读取不会清除脏区域，成功消费后调用 `clear_dirty_bounds()`。
RGBA/非预乘转换、图像编码、GPU View 和零复制映射不包含在首版中。

## 输入事件

页面就绪后，在主线程向 View 发送输入：

```python
from ultralight_py import KeyCode, Modifiers, MouseButton

view.focus()
view.click(40, 80, button=MouseButton.LEFT)
view.input_text("Hello，世界 😀")
view.key_down(KeyCode.GK_BACK)
view.key_up(KeyCode.GK_BACK)
view.scroll(delta_y=-120, x=200, y=200)
```

`mouse_move()`、`mouse_down()`、`mouse_up()` 支持拖动；`click()` 依次发送移动、
按下和释放，不隐式设置焦点。`focus()`、`unfocus()` 控制焦点，
`has_focus` 和 `has_input_focus` 分别查询 View 焦点和可编辑元素焦点。
坐标使用 View 的逻辑像素。滚动默认使用像素，正值向左/上、负值向右/下；
传入 `type=ScrollEventType.PAGE` 可按页滚动，默认坐标 `(-1, -1)` 使用当前指针位置。

需要完整事件字段时，使用不可变的 `MouseEvent`、`ScrollEvent`、`KeyEvent`，分别交给
`fire_mouse_event()`、`fire_scroll_event()`、`fire_key_event()`。
枚举值必须使用对应枚举类型；整数参数按有符号 32 位校验，不接受 bool 或浮点数。
`KeyCode` 保留 SDK 的 `GK_*` 命名，`Modifiers` 支持 ALT、CTRL、META、SHIFT 组合。
鼠标事件的修饰键状态来自最近的键盘事件，宿主需要转发修饰键的按下和释放。

`key_down()` 发送 RAW_KEY_DOWN，不自动输入文本；`key_up()` 发送 KEY_UP。
`input_text()` 按 Unicode 码点发送 CHAR，适合已经提交的文本；它不模拟物理按键，
也不提供输入法预编辑或候选框定位。完整 KeyEvent 可指定原生键码、文本、未修饰文本、
自动重复、小键盘和系统键标志。

输入同样受主线程、对象关闭和运行时占用检查保护。在 Renderer、资源 loader、
JavaScript 桥接或输入回调中再次发送输入会报错；需要追加输入时，将操作排队到宿主下一轮。
输入回调可以关闭 View 或 Runtime。发送事件后仍需持续执行
`update()`、`refresh_display()`、`render()`，尤其是滚动动画。

## Tkinter 适配器与交互示例

Tkinter 适配完全位于可选的 Python 模块中，原生绑定只提供通用输入事件。
普通 `import ultralight_py` 不加载 tkinter，也不要求安装 Pillow。

```python
from ultralight_py.integrations.tkinter import TkInputAdapter

adapter = TkInputAdapter(canvas, view)
# 宿主用 root.after() 驱动 Runtime，并将 copy_pixels() 转成 Tk 图像。
# 关闭窗口时先解除输入绑定，再释放 View 和 Runtime：
adapter.close()
view.close()
runtime.close()
```

适配器自动转发指针、按钮、滚轮、焦点及键盘事件，使用独立 bindtag 保留宿主已有绑定。
窗口失焦时释放按键和按钮，控件销毁时自动解除绑定；`close()` 可重复调用，
只释放自身回调、定时任务和 View 引用，不关闭 View、Runtime 或控件。
如果页面显示区域有缩放或偏移，可传入 `coordinate_transform=lambda x, y: (x, y)`
将控件坐标转换为 View 坐标。

`wheel_pixels=40` 设置每个标准滚轮单位的像素距离；适配器归一化 Aqua、Win32 和 X11
的滚轮差异，Shift+滚轮转为水平滚动，并处理 X11 自动重复的释放事件。
可打印字符与物理按键分开发送，快捷键不会重复插入文本。
macOS Aqua 已完成实际窗口验收；Win32/X11 的映射通过模拟事件测试，尚未完成对应平台实测。

```sh
python examples/tkinter_view.py
python examples/tkinter_view.py --smoke
```

示例包含两个 Python Counter 模型分别控制的按钮、文本框、滚动区域和事件记录，使用标准库将不透明 BGRA 帧转换为 PPM，
通过 Tk Canvas 显示。渲染、窗口尺寸更新和关闭顺序由示例宿主管理。
`--smoke` 创建真实窗口并检查帧尺寸、颜色、Canvas 图像及 Python 模型隔离后自动退出，需要可用的图形环境。

## 构建与测试发行包

```sh
python -m pip install build
python -m build -Ccmake.define.ULTRALIGHT_SDK_ROOT=/absolute/path/to/sdk
python -m pip install --force-reinstall --no-index --find-links=dist 'ultralight-py==0.3.0'
python -m pytest tests -q
```

wheel 包含原生扩展和 UltralightCore、WebCore、Ultralight 动态库，以及内嵌资源。
本地 wheel 的平台标签取决于构建环境；ARM64 wheel 不适用于其他架构，
本地 macOS 26 构建也不代表已经验证旧版 macOS 兼容性。
sdist 包含固定子模块的源码，不要求消费者另行拉取子模块。离线构建应显式提供 SDK；
默认下载复用 ulbind17 的版本固定、校验和缓存逻辑。测试以子进程隔离每个 Runtime 场景，
覆盖离屏渲染、导航、回调释放、线程、异常、HTTP、本地/虚拟资源、输入重入、对象隔离、实时容器、绑定撤销及退出清理。
Tk 测试同时覆盖模拟平台事件和真实窗口；缺少 Tk 或显示服务时跳过真实窗口用例。

后续范围：JS 类构造器、Tk/asyncio 联合循环和其他平台实测。


## macOS Tk 开发环境

项目开发解释器固定为普通 GIL 版本的 Python 3.13.16，Tk 使用 Homebrew 的 Tcl/Tk 8.6。

```sh
brew install tcl-tk@8
env PYTHON_BUILD_HOMEBREW_TCLTK_FORMULA=tcl-tk@8 \
    PYTHON_BUILD_TCLTK_USE_PKGCONFIG=1 \
    PKG_CONFIG_PATH="$(brew --prefix tcl-tk@8)/lib/pkgconfig" \
    pyenv install 3.13.16
pyenv local 3.13.16
python -m tkinter
python -m venv .venv
.venv/bin/python -m pip install build ninja '.[test]'
```

重建已有 `.venv` 前先将旧目录移入 `build/` 备份。
`python -m tkinter` 必须能创建窗口；仅安装 Python 的 tkinter 源码不代表 `_tkinter` 扩展可用。
这套解释器用于开发和实际窗口验收，发行包仍声明 Python 3.10+。

Promise／asyncio 双向桥接与可选定时驱动见 [API 文档](docs/api.md)
和 [示例](examples/async_bridge.py)。
