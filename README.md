# ultralight-py

Ultralight 2.x 的 Python 绑定，用于离屏渲染 HTML 页面，以及在 Python 与 JavaScript 之间共享函数和对象。

- **离屏渲染**：加载 HTML 或网页，执行 JavaScript，读取 CPU 像素帧。
- **双向桥接**：Python 函数、对象与实时容器代理，支持 Promise / asyncio。
- **页面交互**：页面事件与等待、鼠标键盘输入、自定义资源加载，以及可选的 Tkinter 输入适配。

## 安装

需要 Python 3.10+。

```sh
python -m pip install ultralight-py
```

发行 wheel 内含 Ultralight 动态库和运行资源，无需另行安装 SDK。
CI 构建目标为 Windows x64、Linux x64（glibc ≥ 2.34）和 macOS ARM64（11.3+）；
可安装的 wheel 以对应版本的发行文件为准。源码安装见 [开发指南](https://github.com/shabbywu/ultralight-py/blob/main/docs/development.md)。

## 快速开始

加载一段 HTML，执行 JavaScript，并读取渲染后的像素：

```python
import asyncio
from ultralight_py import Runtime
from ultralight_py.scripting import ScriptDriver


async def capture(runtime):
    with runtime.create_view(320, 180) as view:
        async with ScriptDriver.auto(runtime) as driver:
            await driver.page(view).load_html(
                "<style>body{background:#ff0000}</style><body>Hello",
                wait_until="settled",
                timeout=5,
            )
        print(view.evaluate("document.body.textContent"))
        frame = view.copy_pixels()
        print(frame.width, frame.height, frame.format)


with Runtime() as runtime:
    asyncio.run(capture(runtime))
```

引擎操作在 Python 主线程进行。上例由 `ScriptDriver.auto()` 推进页面；
已有 GUI 或宿主循环时，也可以自行驱动 Runtime。像素格式为 BGRA8、预乘 alpha。

## 文档与示例

- [使用指南](https://github.com/shabbywu/ultralight-py/blob/main/docs/guide.md)：页面事件、桥接、资源加载、像素与输入。
- [公开 API](https://github.com/shabbywu/ultralight-py/blob/main/docs/api.md) · [对象桥接](https://github.com/shabbywu/ultralight-py/blob/main/docs/objects.md)。
- [示例](https://github.com/shabbywu/ultralight-py/tree/main/examples)：离屏渲染、双向桥接、虚拟资源、asyncio 和 Tkinter。
- [开发指南](https://github.com/shabbywu/ultralight-py/blob/main/docs/development.md) · [架构](https://github.com/shabbywu/ultralight-py/blob/main/docs/architecture.md) · [发布指南](https://github.com/shabbywu/ultralight-py/blob/main/docs/releasing.md)。
- [更新日志](https://github.com/shabbywu/ultralight-py/blob/main/CHANGELOG.md)。
