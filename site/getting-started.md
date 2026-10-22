# 快速开始

安装 ultralight-py，创建原生窗口，或在离屏页面中执行脚本并读取像素。

## 安装

需要 Python 3.10+。发行 wheel 包含 Ultralight 动态库和运行资源，无需另行安装 SDK。

```sh
python -m pip install ultralight-py
```

CI 构建目标为 Windows x64、Linux x64（glibc ≥ 2.34）和 macOS ARM64（11.3+）。
可安装平台以对应版本的发行文件为准。源码安装见[开发指南](../docs/development.md)。

可选图像依赖：

```sh
python -m pip install 'ultralight-py[pillow,numpy]'
```

## 创建原生窗口

将以下代码保存为 `hello.py`，运行 `python hello.py`。
`API` 在页面首行脚本之前安装注册函数，`Application` 负责窗口与事件循环。

```python
from ultralight_py import API, Application

with API("app") as api, Application() as app:

    @api.register
    def hello(name):
        return f"你好，{name}！"

    window = app.create_window(800, 520, title="Hello, ultralight-py")
    api.attach(window.view)
    window.view.load_html("""
        <style>
          body { background: #111315; color: #edb584;
                 font: 24px system-ui; padding: 48px; }
        </style>
        <h1 id="hello"></h1>
        <script>
          document.querySelector('#hello').textContent = app.hello('世界');
        </script>
    """)
    app.run()
```

`Application` 必须在首次创建 `Runtime` 之前创建。引擎操作在 Python 主线程执行，
引擎关闭后不能在当前进程重新创建。系统字体、输入法和 DPI 由 AppCore 管理。
详见[原生窗口与 API 注册表](../docs/appcore.md)。

## 离屏渲染

不创建窗口时，使用 `Runtime` 创建 CPU 离屏 View。
独立脚本可显式选择 `ScriptDriver.auto()`，在等待期间推进加载与渲染。

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

像素为预乘 alpha 的 BGRA8。`frame.to_rgba()` 返回独立 RGBA 图像；
Pillow、NumPy 及行跨度说明见[像素指南](../docs/guide.md#像素)。
`View.wait_ready()` 等被动等待本身不推进引擎；已有 GUI 循环时由宿主驱动。

## 选择下一步

| 想做什么 | 阅读 |
| --- | --- |
| 查方法、参数和返回值 | [公开 API](../docs/api.md) |
| 创建窗口、注册函数或接入 asyncio | [原生窗口与 API 注册表](../docs/appcore.md) |
| 双向共享 Python 与 JavaScript 对象 | [对象桥接](../docs/objects.md) |
| 自定义资源、处理事件和输入 | [使用指南](../docs/guide.md) |
| 看完整应用、运行效果和示例源码 | [ultralight-py Showcase](https://shabbywu.github.io/ultralight-py-showcase/zh-CN/) |
