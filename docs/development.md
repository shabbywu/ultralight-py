# 开发指南

源码构建、测试和本地开发环境。使用者从 [README](../README.md) 开始；
实现边界见 [架构与维护约定](architecture.md)，发行步骤见 [发布指南](releasing.md)。

## 从源码安装

依赖通过 `externals/pybind11` 和 `externals/ulbind17` 子模块管理。
需要 Python 3.10+、CMake 3.22+ 和支持 C++20 的编译器。

```sh
git submodule update --init --recursive
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test,dev]'
python -c "import ultralight_py"
```

默认下载 Ultralight 2.0.0-beta.2 SDK，也可指定本地 SDK：

```sh
python -m pip install -e . -Ccmake.define.ULTRALIGHT_SDK_ROOT=/absolute/path/to/sdk
```

本地验收以 macOS ARM64、普通 GIL Python 3.13 为主。包要求 Python 3.10+，
其他 Python 版本尚未逐版本完成验收；
Linux x64、Windows x64 保留依赖的构建支持，尚未完成 Python 绑定实测验收。
pybind11 固定 v3.0.4，ulbind17 固定 `3a31b4b`，默认 SDK 固定 2.0.0-beta.2。

## 构建与测试发行包

将安装命令中的路径替换为 `dist/` 中本次生成的 wheel 文件。

```sh
python -m pip install build
python -m build
python -m pip install --force-reinstall /path/to/built.whl
python -m pytest tests -q
```

wheel 包含原生扩展和 UltralightCore、WebCore、Ultralight、AppCore 动态库，以及内嵌资源。
本地 wheel 的平台标签取决于构建环境；ARM64 wheel 不适用于其他架构，
当前系统上的构建不代表已验证旧版 macOS 兼容性。
sdist 包含固定子模块的源码，不要求消费者另行拉取子模块。离线构建应显式提供 SDK；
默认下载复用 ulbind17 的版本固定、校验和缓存逻辑。测试以子进程隔离每个 Runtime 场景，
覆盖离屏渲染、导航、回调释放、线程、异常、HTTP、本地/虚拟资源、输入重入、对象隔离、实时容器、绑定撤销及退出清理。
Tk 测试同时覆盖模拟平台事件和真实窗口；缺少 Tk 或显示服务时跳过真实窗口用例。

## macOS Tk 开发环境

需要运行 Tk 示例时，可使用普通 GIL Python 3.13 和 Homebrew 的 Tcl/Tk 8.6。
以下以 Python 3.13.16 为例：

```sh
brew install tcl-tk@8
env PYTHON_BUILD_HOMEBREW_TCLTK_FORMULA=tcl-tk@8 \
    PYTHON_BUILD_TCLTK_USE_PKGCONFIG=1 \
    PKG_CONFIG_PATH="$(brew --prefix tcl-tk@8)/lib/pkgconfig" \
    pyenv install 3.13.16
pyenv local 3.13.16
python -m tkinter
python -m venv .venv
source .venv/bin/activate
python -m pip install build ninja '.[test,dev]'
```

`python -m tkinter` 必须能创建窗口；仅安装 Python 的 tkinter 源码不代表 `_tkinter` 扩展可用。
这套解释器用于开发和实际窗口验收，发行包仍声明 Python 3.10+。

Promise／asyncio 双向桥接与可选定时驱动见 [API 文档](api.md)
和 [示例](../examples/async_bridge.py)。

## Python 代码检查与格式化

开发依赖包含固定版本的 Ruff。代码检查与格式检查分别运行：

```bash
python -m pip install -e '.[test,dev]'
python -m ruff check .
python -m ruff format --check .

# 自动修复可安全修复的问题并格式化
python -m ruff check --fix .
python -m ruff format .
```

配置位于 `pyproject.toml`，行宽为 100，使用双引号、空格缩进和 LF 换行。
格式化包含源码、类型声明、测试及示例，排除 `externals`、`build` 和 `dist`。

`ruff check` 包含未使用导入等代码检查；`ruff format --check` 只检查格式。
类型声明使用 `typing_extensions.Self`，以保留 Python 3.10 支持。

## AppCore 验收

```sh
python -m pytest tests/test_registry.py tests/test_appcore.py -q
python examples/appcore.py --smoke
python examples/appcore.py --cpu --smoke
```

AppCore 测试需要 macOS 原生桌面会话。其他平台保留注册表回归与安装包加载验证，
原生交互按 [窗口指南](appcore.md#平台验收) 在对应系统验收。
