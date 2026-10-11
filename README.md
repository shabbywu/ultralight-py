# ultralight-py

Ultralight 2.x 的 Python 绑定，支持 CPU 离屏渲染、页面事件、Python/JavaScript
双向函数调用、文档级 JS 句柄，以及 Python 虚拟资源加载。

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

当前实际验收环境为 macOS ARM64、Python 3.13。包要求 Python 3.10+；
Linux x64、Windows x64 保留依赖的构建支持，尚未完成 Python 绑定实测验收。
pybind11 固定 v3.0.4，ulbind17 固定 `4774830`，默认 SDK 固定 2.0.0-beta.2。

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

Python 函数的异常转为页面中的 JS Error。页面事件和资源 loader 的异常被隔离，
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
容器中的嵌套 JSValue 不属于基础容器转换范围。

| Python | JavaScript |
| --- | --- |
| `None` | null |
| `ultralight_py.undefined` | undefined |
| bool | Boolean |
| int、float | Number；JS Number 返回 Python float |
| str | String，保留 Unicode 和内嵌 NUL |
| list、tuple | Array；稀疏数组的空洞转换为 undefined |
| 字符串键 dict | 无原型的数据对象，`__proto__` 作为普通键 |

Python int 必须位于 ±(2⁵³−1)，不进行隐式字符串/数字转换。JS 数组与普通对象递归转换为
list/dict；函数、Promise、Date 等特殊对象通过 JSValue 使用。循环引用或超过 64 层的容器
报 `TraversalLimit`。重复的兄弟节点允许转换，但转换结果不保留对象别名。
对象转换会读取自有可枚举字符串属性，可能执行 getter；`keys()` 不读取属性值。

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

## 构建与测试发行包

```sh
python -m pip install build
python -m build -Ccmake.define.ULTRALIGHT_SDK_ROOT=/absolute/path/to/sdk
python -m pip install dist/ultralight_py-*.whl
python -m pytest tests -q
```

wheel 包含原生扩展和 UltralightCore、WebCore、Ultralight 动态库，以及内嵌资源。
sdist 包含固定子模块的源码，不要求消费者另行拉取子模块。离线构建应显式提供 SDK；
默认下载复用 ulbind17 的版本固定、校验和缓存逻辑。测试以子进程隔离每个 Runtime 场景，
覆盖离屏渲染、导航、回调释放、线程、异常、HTTP、本地/虚拟资源和退出清理。

后续范围：Python 对象代理、输入事件、Promise/asyncio 和其他平台实测。


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
