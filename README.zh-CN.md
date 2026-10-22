# ultralight-py

[English](README.md) · 简体中文

Ultralight 2.x 的 Python 绑定，用于离屏渲染、AppCore 原生窗口，以及在 Python 与 JavaScript 之间共享函数和对象。

[中文文档](https://ultralight-py.shabbywu.cn/zh-CN/) · [English docs](https://ultralight-py.shabbywu.cn/en/) · [API 文档](https://ultralight-py.shabbywu.cn/zh-CN/api.html) · [示例展示](https://shabbywu.github.io/ultralight-py-showcase/zh-CN/)

- **原生窗口**：AppCore 系统字体、DPI、输入与 IME，共用 asyncio 循环，见 [窗口指南](docs/appcore.md)。
- **独立 API 注册表**：装饰器注册函数、导出对象、加载前附着与导航恢复。
- **离屏渲染**：加载 HTML 或网页，执行 JavaScript，读取 CPU 像素帧。
- **Session 隔离**：同账号多 View 共享浏览器存储，不同 Session 隔离；支持临时和持久化存储，见 [示例](examples/sessions.py)。
- **双向桥接**：Python 函数与对象，list/dict ↔ Array/Object 双向共享，支持原生 JS 容器操作与 Promise / asyncio。
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
`frame.to_rgba()` 返回独立的 RGBA 图像；可选 Pillow/NumPy 输出见 [像素指南](docs/guide.md#像素)。

## 游戏 Demo

[Emberkeep](https://github.com/shabbywu/emberkeep) 是基于 ultralight-py 0.5.0 实现的桌面像素 Roguelike，包含回合制战斗、随机地牢、升级和存档续玩，并支持中英文界面。

Python 负责游戏规则，JavaScript Canvas 负责画面与 UI，通过注册函数、实时对象代理和 Promise 双向桥接。它展示了 AppCore 原生窗口、asyncio 循环、自定义资源加载与对象桥接在完整游戏中的应用。

运行方式、操作说明和下载入口见 [Emberkeep README](https://github.com/shabbywu/emberkeep/blob/main/README.zh-CN.md)。

## 文档与示例

在线阅读[中英双语文档站](https://ultralight-py.shabbywu.cn/zh-CN/)，支持语言切换及 API 与指南全文搜索；完整应用、原生运行效果和示例源码见 [Showcase](https://shabbywu.github.io/ultralight-py-showcase/zh-CN/)。

- [使用指南](https://github.com/shabbywu/ultralight-py/blob/main/docs/guide.md)：页面事件、桥接、资源加载、像素与输入。
- [公开 API](https://github.com/shabbywu/ultralight-py/blob/main/docs/api.md) · [对象桥接](https://github.com/shabbywu/ultralight-py/blob/main/docs/objects.md)。
- [示例](https://github.com/shabbywu/ultralight-py/tree/main/examples)：离屏渲染、双向桥接、虚拟资源、asyncio 和 Tkinter。
- [开发指南](https://github.com/shabbywu/ultralight-py/blob/main/docs/development.md) · [架构](https://github.com/shabbywu/ultralight-py/blob/main/docs/architecture.md) · [发布指南](https://github.com/shabbywu/ultralight-py/blob/main/docs/releasing.md)。
- [更新日志](https://github.com/shabbywu/ultralight-py/blob/main/CHANGELOG.md)。
