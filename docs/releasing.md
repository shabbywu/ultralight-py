# 发布指南

本文面向仓库维护者，记录多平台构建、发行包验收及 PyPI 发布步骤。
本地构建见 [开发指南](development.md#构建与测试发行包)。

## 多平台 CI 与人工审批发布

[Wheels 工作流](../.github/workflows/wheels.yml) 构建普通 GIL CPython 3.10–3.14 的
Windows x64、Linux x64、macOS ARM64 wheel，共 15 个 wheel 和一个 sdist。
Linux 发行基线为 **glibc ≥ 2.34**；macOS 部署目标为 **11.3**（macOS 11.x 的 wheel
标签统一为 `macosx_11_0_arm64`）。这些是 CI 的验收目标；一次运行只有所有构建、
依赖修复及安装测试通过后，才会生成完整发行 artifact。

在 GitHub Actions 选择 **Wheels → Run workflow**，选择分支并保持 `publish=false`，
可进行试构建。分支上选择 `publish=true` 会在构建前失败。
正式发布先让 `pyproject.toml` 和 `CMakeLists.txt` 的版本一致，创建对应的 `vX.Y.Z` tag，
再发布该 tag 的 GitHub Release；也可选择该 tag 手动运行并勾选 `publish`。
正式发布的 tag 必须与包版本完全匹配。仅创建 tag 不会自动发布。
同一 ref 的运行不互相取消；GitHub 的 concurrency 仅保留一个运行和一个待运行项，
更晚的触发可能替换待运行项，因此请避免连续重复触发。

工作流先构建并检查 sdist，再从该源码包构建 wheel，使用 auditwheel、delocate 和
delvewheel 修复动态库依赖，逐个在独立环境安装 wheel 后运行现有测试。
测试文件复制到临时目录，清除 `PYTHONPATH` 和 SDK 动态库搜索变量；
核心原生用例必须执行，Tk 缺失时沿用现有跳过行为。源码提交和 SDK 版本固定，
审批后直接上传本次构建的文件，不重新编译。

在运行摘要下载 `release-packages` 和 `release-manifest`，artifact 保留 30 天。
前者仅含 wheel 与 sdist，后者包含 `manifest.json` 和 `SHA256SUMS`，记录提交 SHA、
SDK 版本、文件大小、平台及 SHA-256。解压后，用 Python 3.11+ 和本次提交的校验脚本检查：

```sh
python -m pip install packaging
python scripts/release.py verify --directory /path/to/release-packages \
  --manifest /path/to/release-manifest/manifest.json \
  --version 0.4.0 --commit <运行摘要中的完整提交SHA>
```

在三种平台分别用匹配的 Python 创建全新虚拟环境，从 artifact 安装对应 wheel。
下载并解压 sdist，将其中的 `tests/`、`examples/`、`scripts/test_wheel.py` 复制到
另一个空目录（保持相对路径），进入该目录运行：

```sh
python -m pip install /absolute/path/to/matching.whl 'pytest>=8,<10' 'pytest-asyncio>=1,<2'
python -I scripts/test_wheel.py
```

无需提供外部 Ultralight SDK。Linux 测试环境需要 Xvfb、X11、字体及相关系统运行库，
使用 `xvfb-run -a python -I scripts/test_wheel.py`；CI 使用的安装列表见
`pyproject.toml` 的 `tool.cibuildwheel.linux.before-all`。
人工确认像素、透明度、资源、HTTP、输入、对象 Bridge、asyncio、缓存及释放测试结果后，
在本次运行的 **Review deployments → pypi** 审批。拒绝审批不会上传；
批准后会再次核对整套文件与清单，仅上传这些文件。已存在的 PyPI 版本会发布失败，
不会跳过重复文件。超过 artifact 保留期须重新构建并验证。

仓库维护者需要完成以下外部配置（工作流文件无法代替这些设置）：

- GitHub **Settings → Environments → pypi**：Required reviewers 设置为 `shabbywu`，
  允许维护者自行审批（关闭 Prevent self-review），关闭管理员绕过保护规则，
  Deployment branches and tags 选择仅允许 **Tag** 类型的 `v*`。
  Required reviewers 的可用性取决于仓库可见性和 GitHub 方案；必须确认审批规则已实际启用。
  仅写 `environment: pypi` 不会自动启用人工审批，见
  [GitHub Environment 官方说明](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)。
- PyPI 为 `ultralight-py` 配置 Trusted Publisher：Owner `shabbywu`，Repository `ultralight-py`，
  Workflow `wheels.yml`，Environment `pypi`。使用 OIDC，无需保存 PyPI API Token，见
  [PyPI Trusted Publisher 官方说明](https://docs.pypi.org/trusted-publishers/using-a-publisher/)。

仅 `publish_pypi` job 有 `id-token: write` 权限；其他 job 仅有 `contents: read`。
本工作流不添加 PR 全矩阵构建、TestPyPI 或 GitHub Release 附件上传。
