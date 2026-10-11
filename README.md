# ultralight-py

Ultralight Python 绑定项目框架，尚未实现功能接口。

依赖通过 `externals/pybind11` 和 `externals/ulbind17` 子模块管理。
需要 Python 3.10+、CMake 3.22+ 和支持 C++20 的编译器。

```sh
git submodule update --init --recursive
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -c "import ultralight_py"
```

默认下载 Ultralight 2.0.0-beta.2 SDK，也可指定本地 SDK：

```sh
python -m pip install -e . -Ccmake.define.ULTRALIGHT_SDK_ROOT=/absolute/path/to/sdk
```
