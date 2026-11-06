# 源码与补丁维护

更新：2026-11-05。[原始说明](source-layout-history-20261104.md)保留早期5/24目标阶段；当前清单以开发工作区文件为准。[文档总索引](README.md)。

## 应修改哪里

`local_deep_research/`是实际部署补丁目录，不是完整可启动应用。`local-deep-research/`是旁置上游源码快照，有自己的src布局、依赖、工具链和测试，可能与固定运行镜像不同；只修改这份上游快照不会自动部署。本机其他同名目录也不是当前5002构建入口。

5002代码工作区为`/data/ningh/nh/astro-dra-ui-5002`，分支`work/ui-5002-20261028`；main工作区为`/data/ningh/nh/astro-dra`。构建和运行配置目录的差别见[部署说明](deployment.md)。

## 当前安装集合

| 集合 | 当前数量 | 用途与入口 |
| --- | --- | --- |
| 应用后端/既有JS覆盖目标 | 24 | 任务、Agent、搜索、相关性、抓取、引用、报告、存储/装配及原生模型选择 |
| 工作台/UI覆盖目标 | 29 | 模板、样式、中文词典/显示层、主题、侧栏、角色页面与简化表单 |
| 应用覆盖目标合计 | 53 | [完整manifest](../deployment/overlay-manifest.json)；其中UI另有[子清单](../deployment/ui-overlay-manifest.json) |
| research_verify独立模块 | 32个Python文件，已部署5002 | 身份、材料、子任务交付、核对、publication及trace，也含历史兼容和CLI |
| astro_accounts独立模块 | 5个Python文件 | store、web、policy、cli及包入口 |
| 原生账号钩子目标 | 7个文件 | [账号安装器](../deployment/install_accounts.py)检查明确位置后安装，不能简单当作上述manifest文件 |

`install_overlays.py`通过活动解释器定位包、验证源语法及目标，再安装；完整安装还追加Agent的COLLECTION_HOOK。账号安装器随后修改app_factory、认证路由、settings manager、encrypted_db、auth_db、research_routes及调度器。对比包内文件应计入这些转换。

2026-11-04新增`research_verify/subtask_handoff.py`，已随Agent部署到5002。常规构建由既有包复制安装覆盖，Agent覆盖目标不新增；本次定向部署仅替换Agent并新增模块，继承其他已部署内容，见[子任务交付](subtask-handoff-20261104.md)。

随后新增`research_verify/subtask_research.py`，负责有界检索、独立交付及按子任务保全消息/来源，11月5日已随第二版部署5002；实际三目标安装SHA与昨日最终测试镜像相符。见[第二版](subtask-handoff-v2-20261104.md)及[部署](subtask-handoff-v2-deploy-5002-20261105.md)。

11月5日开发候选新增`research_verify/source_reading.py`，在写作前选取原句及其原文主体/状态并分组，和选段/范围修补一起构成[第三版](subtask-scope-v3-20261105.md)。942包文件相对第二版仅5个辅助模块变化；11月5日13:48:57已将相同测试镜像部署5002，安装文件SHA一致，见[部署测试](subtask-scope-v3-deploy-5002-20261105.md)。共享generation和evidence_flow的synthesize写作部分已改，核查函数保持。

## 构建入口

- [完整Dockerfile](../deployment/Dockerfile)：固定上游镜像digest，安装ddgs、完整后端/UI及账号模块。
- [UI Dockerfile](../deployment/Dockerfile.ui)：仅在指定现有镜像上覆盖UI，不安装完整后端/账号钩子；基础标签较早，使用前核对继承功能。
- [账号Dockerfile](../deployment/Dockerfile.accounts)：基于指定既有sidebar镜像安装账号和UI，用于当时分层部署。
- `deployment/*-overlay-manifest.json`中其他检索/收集/来源/trace子清单记录阶段性定向补丁范围，不能当作当前完整安装清单。
- `local_deep_research/Dockerfile`及旧Compose为原部署入口；5000通过私有覆盖文件已指定根目录完整构建方式。

## 代码与验证对应

| 修改内容 | 先查看 | 主要验证入口 |
| --- | --- | --- |
| 检索、来源、写作、核对 | [当前流程](current-research-flow-20261016.md)及对应日期记录 | `local_deep_research/tests/`；必要时隔离真实检索/模型及保存导出 |
| 工作台、中文、主题、侧栏 | [UI维护说明](../local_deep_research/overlay/ui/README.md)及对应日期记录 | `scripts/check_*_ui.cjs`；依赖隔离预览与测试账号，部分脚本会操作数据 |
| 模型选择表单 | `overlay/research.js`、`settings_sync.js` | `node scripts/check_model_selection.cjs`，离线VM |
| 账号与配置策略 | [账号说明](account-roles-5002-20261102.md) | `test_account_roles.py`、隔离`check_accounts_runtime.py`和`check_account_ui.cjs` |
| 部署/代理 | [部署](deployment.md)、[连通性](search-connectivity-20261028.md) | Compose插值、镜像安装检查；实际三源探针属于联网验证 |

根`requirements-test.txt`仅提供独立模块回归依赖，不能代替完整上游应用环境。基础digest和ddgs版本已固定，传递依赖尚未完全锁定。成功安装、403回归或页面正常均不能单独证明研究质量。
