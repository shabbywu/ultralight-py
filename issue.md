# Ultralight Python 绑定需求与完成状态

开发 `/Users/shabbywu/workplace/python/ultralight-py`，为 Ultralight 提供 Python 绑定。
核心功能及本地发行包验收已完成，验证范围限定为 macOS ARM64。正式发布时另行确定版本号。

## 已完成范围

1. Runtime／Renderer／View 的创建、更新、渲染和释放，以及主线程与关闭约束。
2. 页面加载、JavaScript 求值、加载事件、控制台及错误回调。
3. Python/JavaScript 基础类型转换、函数调用、JSValue、Python 实例及容器实时代理。
4. CPU 离屏像素访问、鼠标、滚动、键盘输入和可选 Tk 输入适配。
5. Python 虚拟资源加载、本地资源回退、SDK 内嵌资源及动态库打包。
6. 示例、公开 API 与架构文档、类型声明、关键生命周期测试。
7. Promise/asyncio 双向桥接、可选定时驱动器，以及取消、解绑、导航和关闭清理。
8. 私有模块职责拆分、绝对模块导入和 Ruff lint／格式检查。

## 依赖与职责

- pybind11 子模块固定 v3.0.4（`d03662f`）。
- ulbind17 子模块固定 `670910c`，默认 SDK 固定 Ultralight 2.0.0-beta.2。
- 支持通过 `ULTRALIGHT_SDK_ROOT` 指定本地 SDK。
- Python 类型转换、对象封装、异常处理、GIL 和 Python 引用管理在本项目实现；
  通用运行时、Bridge、文档失效、资源和 PostTask 能力复用 ulbind17／SDK。
- 采用 C++20、CMake 和 scikit-build-core；发行包名 `ultralight-py`，导入名 `ultralight_py`。
- Python 包声明 3.10+；本轮实际验证使用普通 GIL Python 3.13.16。

## 验收范围

本轮仅验证 macOS ARM64，不声明其他操作系统、架构或 Python 版本已通过验收。
已从 sdist 构建 wheel，在全新环境安装后通过 70 项测试、全部示例及 Ruff 检查。

## 当前边界

- Renderer 每进程唯一，关闭后不能重建；引擎操作限定主线程。
- Python 宿主负责更新和渲染；await 不隐式调用 update。
- 不包含 GPU View、零复制像素、JS 类构造器、输入法预编辑、Tk/asyncio 联合循环或 JS AbortSignal。
- 不包含 CI/CD 和发行包上传。

## 维护要求

明确对象所有权、线程约束和回调释放规则，保留固定依赖及可复现构建。
遵循仓库 AGENTS.md，代码发现优先使用 codebase-memory-mcp。
按历史习惯使用简洁的中文提交说明；本轮不修改已有提交历史。
