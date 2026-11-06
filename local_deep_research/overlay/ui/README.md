# 工作台前端覆盖

此目录覆盖实际安装的Flask/Jinja前端，由deployment/ui-overlay-manifest.json管理；不使用旁置新版上游目录。

- templates/：页面覆盖；保留原控件id/name和API入口。
- astro-workspace.css/js：工作台布局和阅读增强。
- theme.js：浅色/深色/跟随系统；存储值仍light/hashed/system。
- astro-locale-zh.js：内置UI中文词典，不放用户内容或凭据。
- astro-i18n.js：显示层本地化与动态控件处理。
- native/：原生UI的必要兼容改动；升级上游时应重新比较，避免覆盖新逻辑。

新增UI可调用window.AstroI18n.t(text)，只用于显示，不能将译文作为模型ID、配置键、路由、请求字段或研究提示词。文字驱动的判断应使用data属性/固定标识。为新的用户内容区域加translate="no"或data-astro-content；不要删掉现有保护区域，也不要翻译输入value或已保存报告。

动态词条使用{{0}}等占位符并保留变量；分页等数字占位符与文本变量区分。维护同名词的语境，避免把Page Size作为Page N。未知词条应保留原文，不能依赖对象原型字段或猜测译文。

部署用deployment/Dockerfile.ui，只叠加UI，保留现有后端。验证入口scripts/check_chinese_ui.cjs（隔离环境），另外保留check_workspace_ui.cjs与check_theme_ui.cjs。具体部署/限制见docs/ui-chinese-20261030.md。
