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
- `site/assets/`：样式、脚本和图标；语法高亮 CSS 在构建时生成。
- `scripts/build_site.py`：页面清单、Markdown 渲染、链接转换、页内目录和搜索索引生成。

正式公开地址由 `scripts/build_site.py` 的 `BASE_URL` 常量指定，用于 canonical、语言替代链接、站点地图和 robots.txt。

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

## 反向代理与公开域名

正式入口为 `https://ultralight-py.shabbywu.cn/`，通过其他站点反向代理中转到 GitHub Pages。
GitHub Pages 使用原有项目地址 `https://shabbywu.github.io/ultralight-py/` 作为源站。
域名、证书与回源配置由代理及中转站管理；Pages 的 Custom domain 保持为空。

公开入口使用域名根路径，回源时由代理链路映射到源站的 `/ultralight-py/` 前缀，例如
`/en/api.html` 最终对应源站 `/ultralight-py/en/api.html`。
静态资源和搜索索引使用相对路径；canonical、hreflang、og:url 和 sitemap 始终使用 `BASE_URL` 中的公开域名。
代理应提供有效的 HTTPS 证书，并公开转发 `/robots.txt`、`/sitemap.xml` 和页面、资源请求。
若中转站有自己的 robots.txt，需要让公开域名的 `/robots.txt` 声明本站的 sitemap 地址。

构建会清理旧产物中的 `CNAME` 文件，避免遗留之前的 Pages 域名配置。

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
