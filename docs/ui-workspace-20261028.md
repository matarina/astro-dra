# 5002 研究工作台界面（2026-10-28）

> 文档定位：已部署5002；未合入main。本页记录当时过程；当前状态见[状态总览](current-status.md)，有效后续见[待办](roadmap.md)。

本轮按用户要求优化本地5002界面，独立分支 `work/ui-5002-20261028`，基于合并后的main `e9be103`；主工作区尚未提交的README和部署说明保留原样。已部署5002，5000未更新。

## 页面与代码

界面使用LDR原有Flask/Jinja模板和原生JavaScript组件，未增加前端框架。

- `local_deep_research/overlay/ui/templates/`：登录、注册、公共布局、导航、研究首页、进度、报告及历史记录，共8个模板。
- `local_deep_research/overlay/ui/astro-workspace.css`：工作台样式、浅色/深色配色、响应式布局与打印样式，位于原生样式之后加载。
- `local_deep_research/overlay/ui/astro-workspace.js`：字数提示、通用问题模板、配置入口、手机导航、密码可见切换、报告目录和专注阅读。
- `deployment/ui-overlay-manifest.json`：只含上述10个UI安装目标；完整manifest也已包含这些目标，供后续完整构建使用。
- `deployment/Dockerfile.ui`：从现有运行镜像只叠加UI；installer的 `--ui-only` 会拒绝非UI目标，提前解析Jinja模板，且不安装research_verify、不更新检索默认值或collector。

首页采用灰白底色、绿色主按钮和侧栏，保留原主题偏好；可用通用模板补充问题，并显示当前模型。报告增加章节目录和专注阅读，次要操作收纳进更多操作，导出与追问沿用原组件。登录/注册采用统一布局。手机提供侧栏抽屉，报告内容自适应。进度页的三个步骤仅用于解释流程，实际状态与百分比仍由原生组件提供。

原模板的全部DOM id和表单name保留；模型、搜索、策略、隐私范围及导出接口仍走原有实现。未改研究提示词、来源处理、引用编号、报告正文或模型配置。原有告警内容保留并统一排版。部分高级配置和动态消息继续使用原生英文。

## 验证

- 394项现有Python回归通过；JavaScript语法、模型选择/提交回归与diff空白检查通过。
- Playwright/Chromium在独立数据卷、仅监听127.0.0.1:15002的预览容器验证登录、密码可见切换、注册必选项、问题模板、详细模式、模型实际提交参数、导出菜单、报告目录、专注阅读、手机菜单和横向溢出；无页面JavaScript异常。
- 研究提交被浏览器拦截，没有为界面验收启动真实研究。报告使用明确标注的模拟Markdown，覆盖标题、表格和参考文献；截图不表示真实文献质量验证。
- 生产原镜像927个包内文件逐个SHA比较，新镜像仅8模板+2资源发生变化；部署后文件与已验收镜像一致。生产只检查公开登录页、静态资源和安装文件，没有创建测试账号或读取用户报告。
- 构建验证采用 `deployment/Dockerfile.ui`；本轮没有重新运行通用完整镜像构建。

隔离环境复测命令（使用已有一次性账号，凭据JSON不提交）：

```bash
UI_BASE_URL=http://127.0.0.1:15002 \
UI_TEST_USER_FILE=/private/path/test-user.json \
UI_ARTIFACT_DIR=/private/path/screenshots \
NODE_PATH=/path/to/playwright/node_modules \
node scripts/check_workspace_ui.cjs
```

此脚本只应在独立预览环境运行。Playwright依赖本轮安装在仓库外，不添加到应用运行依赖中。

## 部署与恢复

部署镜像 `astro-dra:ui-5002-20261028`，image ID `sha256:8d2548309befda0d80a283cbcd7962d9f1f2bda962952c8e6aaea44aeda3ac88`。只更改主工作区私有 `.env.test-5002` 中ASTRO_DRA_IMAGE，只重建5002应用，容器healthy、登录HTTP200，实际CSS/JS与源码SHA一致。模型仍为deepseek-v4-flash；环境变量、两个数据卷不变。5000应用、5002搜索与代理容器的ID/启动时间均保持不变。

复建UI镜像：

```bash
docker build -f deployment/Dockerfile.ui \
  --build-arg LDR_UI_BASE_IMAGE=astro-dra:review-repairs-20261027 \
  -t astro-dra:ui-5002-20261028 .
```

部署前配置及运行元数据保存在 `/data/ningh/nh/ldr-test-5002-backups/ui-20261028-135302`，含私密环境变量，不提交。需要恢复时，在主工作区恢复其中env文件，使用原Compose项目名 `astro-dra-test-5002` 和 `up -d --no-build --no-deps --force-recreate local-deep-research`，回到 `astro-dra:review-repairs-20261027`。不删除或恢复数据卷。

## 预览

截图来自隔离预览账号，报告为模拟数据。

[首页](ui-workspace-20261028/ui-home-desktop.png) · [报告阅读](ui-workspace-20261028/ui-report-desktop.png) · [登录](ui-workspace-20261028/ui-login-desktop.png) · [手机首页](ui-workspace-20261028/ui-home-mobile.png) · [深色首页](ui-workspace-20261028/ui-home-dark.png)

部署核对字段见 [JSON](ui-workspace-20261028.json)。私有浏览器产物和凭据位于仓库外 `/data/ningh/nh/ldr-experiments/ui-5002-20261028`。后续可根据用户实际操作反馈调整密度与布局；代码尚未提交、推送或合并。
