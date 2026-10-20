# 发布指南

本文记录发行包构建、验收和 PyPI 发布步骤。本地构建见 [开发指南](development.md#构建与测试发行包)。

## 构建与触发

[Wheels 工作流](../.github/workflows/wheels.yml) 构建普通 GIL CPython 3.10–3.14 的
Windows x64、Linux x64 和 macOS ARM64 安装包，共 15 个 wheel 和一个源码包。
Linux 基线为 glibc 2.34，macOS 部署目标为 11.3，安装包标签为 `macosx_11_0_arm64`。
原生扩展及 UltralightCore、WebCore、Ultralight、AppCore 动态库随包发行。

在 GitHub Actions 中手动运行 `Wheels`，保持 `publish=false` 可试构建分支。
正式发布先统一 `pyproject.toml` 与 `CMakeLists.txt` 的版本，再创建对应的 `vX.Y.Z` 标签，
发布该标签的 GitHub Release；也可手动选择标签并启用 `publish`。
只有匹配包版本的标签允许发布，单独创建标签不会触发发布。

工作流先校验源码包，再从源码包构建安装包。动态库依赖分别由 auditwheel、delocate 和
delvewheel 修复，随后在独立环境安装并测试。源码提交和 SDK 版本固定；
全部检查通过后生成发行产物，人工批准后上传这些文件，不重新编译。

## 下载与验收

运行摘要提供 `release-packages` 和 `release-manifest`，保留 30 天。
前者包含安装包和源码包；后者包含 `manifest.json`、`SHA256SUMS`，
记录源提交、SDK 版本、文件大小、平台和校验和。

使用 Python 3.11+ 校验完整发行包集合，将版本号和提交 SHA 替换为本次构建值：

```sh
python -m pip install packaging
python scripts/release.py verify --directory /path/to/release-packages \
  --manifest /path/to/release-manifest/manifest.json \
  --version 0.6.1 --commit 完整提交SHA
```

在各目标平台创建全新虚拟环境并安装匹配的安装包。将源码包中的 `tests/`、`examples/`
和 `scripts/test_wheel.py` 复制到另一个空目录，保持相对路径，在该目录运行：

```sh
python -m pip install /absolute/path/to/matching.whl \
  'pytest>=8,<10' 'pytest-asyncio>=1,<2' 'Pillow>=11,<13' 'numpy>=1.26,<3'
python -I scripts/test_wheel.py
```

验收使用包内 SDK 运行库，不提供外部 SDK。Linux 需要 Xvfb、X11、字体及相关系统库，
使用 `xvfb-run -a python -I scripts/test_wheel.py`；依赖列表见 `pyproject.toml`。
Tk 与 AppCore 原生窗口用例需要相应桌面环境，AppCore 桌面测试目前以 macOS 为验收目标。
另外运行 [窗口示例](../examples/appcore.py)，检查中文字体、输入法、尺寸调整和跨屏 DPI。

## 审核与发布

确认安装、资源、像素、输入、对象桥接、Session、asyncio 与释放测试结果后，
在本次运行的部署审核页面批准 `pypi`。批准后再次校验文件和清单，并上传到 PyPI。
拒绝审核不会上传；同版本已存在时发布失败。产物过期后需要重新构建和验收。

维护者需完成仓库外部配置：

- GitHub 中配置受保护的 `pypi` 环境：审核者设为 `shabbywu`，允许自行审核，
  禁止管理员绕过，仅允许 `v*` 标签部署。保护规则需在 GitHub 实际启用，
  工作流中的环境名称不会自动创建审核规则。参见 [环境保护说明](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)。
- PyPI 中为 `ultralight-py` 配置可信发布者：所有者 `shabbywu`、仓库 `ultralight-py`、
  工作流 `wheels.yml`、环境 `pypi`。通过 OIDC 发布，无需保存 API 令牌。
  参见 [可信发布者配置](https://docs.pypi.org/trusted-publishers/using-a-publisher/)。

仅发布作业持有 `id-token: write`，其他作业只持有 `contents: read`。
