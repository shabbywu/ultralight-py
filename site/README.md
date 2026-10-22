# GitHub Pages 文档站

本站延续 ultralight-godot 与 ultralight-py-showcase 的深色、暖杏色视觉风格。
首页、API、指南和全文搜索均静态生成，无 CDN、运行时服务或原生 SDK 依赖。
提供完整的简体中文与英文内容，示例入口链接至 [Showcase](https://shabbywu.github.io/ultralight-py-showcase/) 相同语言的对应章节。

## 本地构建与预览

在仓库根目录执行（Python 3.10+）：

```sh
python -m pip install -r site/requirements.txt
python scripts/build_site.py
python -m http.server 8000 --directory dist
```

打开 <http://localhost:8000/>。生成结果位于 Git 忽略的 `dist/`。
中文入口为 <http://localhost:8000/zh-CN/>，英文入口为 <http://localhost:8000/en/>。
根目录保留原有中文页面地址，语言切换会进入 `/zh-CN/` 或 `/en/` 中的对应文档。
也可把 `dist/` 挂在 `/ultralight-py/` 等子路径，页面资源和搜索使用相对地址。
请通过 HTTP 预览，搜索索引通过 fetch 加载。

## 内容维护

- `docs/*.md` 和 `CHANGELOG.md`：中文 API、指南和变更记录。
- `docs/en/*.md`：英文 API、指南和更新日志，按对应中文文件维护完整翻译。
- `site/getting-started.md`、`site/en/getting-started.md`：中英文快速开始；首页窗口代码从对应语言的第一个 Python 代码块生成。
- `site/index.html`、`site/en/index.html`：中英文首页、API 索引和 Showcase 链接。
- `site/locales/zh-CN.json`、`site/locales/en.json`：导航、搜索、复制提示和无障碍标签等界面文案。
- `site/layout.html`：公共页头、页脚和搜索弹窗。
- `site/config.json`：正式站点的 HTTPS 域名，用于 canonical、语言替代链接、站点地图和 robots.txt。
- `site/assets/`：样式、脚本和图标；语法高亮 CSS 在构建时生成。
- `scripts/build_site.py`：页面清单、Markdown 渲染、链接转换、页内目录和搜索索引生成。

新增文档时同时加入 `PAGES` 和 `EN_PAGES`，再按用途调整侧栏分组。
中英文同一文档的标题层级和顺序须一一对应；构建会检查并生成对应章节的锚点映射，语言切换时保留章节位置。
中文标题保留中文 ID，英文使用英文 ID。修改标题后同步更新本语言内的 Markdown 链接和首页 API 索引。
文档之间的相对 Markdown 链接转为当前语言目录下的 HTML 链接；示例代码、工作流等仓库文件链接转为 GitHub 地址。
修改内容后重新构建即可同步各语言的全文搜索索引。
构建会检查翻译页面清单、标题层级、界面翻译键、所有生成页面的站内链接、资源文件、重复 ID 和搜索结果锚点；错误时中止发布。

## 发布

仓库 Settings → Pages → Build and deployment → Source 选择 **GitHub Actions**。
`.github/workflows/pages.yml` 会在相关文件推送到 `main` 时构建并部署，也支持手动触发。
PR 仅构建站点。无需拉取子模块或构建 Python 绑定。

默认部署地址：[中文](https://ultralight-py.shabbywu.cn/zh-CN/) · [English](https://ultralight-py.shabbywu.cn/en/)。
首次启用 Pages 后可手动运行 **Documentation Pages** 工作流。

## 自定义域名

正式域名为 `ultralight-py.shabbywu.cn`，构建配置位于 `site/config.json`。
部署路径为域名根目录，不再包含 `/ultralight-py/`。

1. 在仓库 **Settings → Pages → Custom domain** 填写 `ultralight-py.shabbywu.cn` 并保存。
2. 若直接使用 GitHub Pages，在 `shabbywu.cn` 的 DNS 中添加：

   | 类型 | 主机记录 | 目标 |
   | --- | --- | --- |
   | CNAME | `ultralight-py` | `shabbywu.github.io` |

   若保留 EdgeOne 等 CDN，由 CDN 将该域名的请求回源至此 Pages 站点，保留正确路径和 HTTPS，
   并确保 HTML、`robots.txt` 和 `sitemap.xml` 可以被公开访问。
3. 直连 Pages 时等待 DNS 和证书生效后，在 Pages 设置启用 **Enforce HTTPS**。

构建会生成 `dist/CNAME`，供按分支发布时使用。
当前使用自定义 GitHub Actions 发布，GitHub 会忽略该文件；**仍须在 Pages 设置中绑定域名**。
参考 [GitHub 自定义域名文档](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site)。

## 站点地图与 Google Search Console

构建自动输出：

- `sitemap.xml`：中英文首页及各 9 篇文档，共 20 个正式 URL。
- `robots.txt`：允许抓取并声明正式域名上的 sitemap 地址。
- HTML 中绝对地址的 canonical、双语 hreflang、x-default 和 og:url。
- 404 页面标记 `noindex`；原有根目录中文页面的 canonical 指向 `/zh-CN/`，不重复列入 sitemap。

正式提交地址：<https://ultralight-py.shabbywu.cn/sitemap.xml>。
新增文档会自动进入 sitemap；未使用构建时间冒充内容最后修改时间。

`shabbywu.cn` 已通过 Google Search Console 的 DNS 验证，无需再添加 HTML 验证标签。
站点部署生效后，在已有 `shabbywu.cn` Domain 资源的 **Sitemaps / 站点地图** 中提交上述完整 URL。
也可以为 `https://ultralight-py.shabbywu.cn/` 新增 URL 前缀资源，使用父域已验证的所有权。
提交后可用网址检查查看中英文页面的抓取及索引状态。
仓库构建生成接入所需文件；在 Search Console 中提交需由已登录的站点所有者操作。

参考 [Google 站点地图说明](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)
和[所有权验证说明](https://support.google.com/webmasters/answer/9008080)。

## 交互与兼容性

文档、导航、目录和链接无需 JavaScript 即可阅读。JavaScript 提供全文搜索、
⌘/Ctrl K 快捷键、目录当前位置和移动端导航折叠。
代码复制需要支持 Clipboard API 的安全上下文（HTTPS 或 localhost）。
搜索弹窗支持方向键、Enter 和 Esc；减少动态效果遵循系统偏好。
