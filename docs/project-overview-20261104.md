# LDR 项目接续概览（2026-11-04）

> 文档定位：2026-11-04初次熟悉项目的基线快照。后续现状以[当前状态](current-status.md)为准，全部资料见[总索引](README.md)。

本轮按用户要求熟悉当前目录及 Astro DRA，核对源码、Git、部署和离线测试。后续开发先在5002验证，测试完成后再合入main，随后同步5000。本轮只增加接续文档，没有修改应用代码、配置、数据或运行服务，也未提交、推送或合并。

## 工作区与运行实例

| 项目 | 5000主实例 | 5002开发测试实例 |
| --- | --- | --- |
| 代码工作区 | `/data/ningh/nh/astro-dra` | `/data/ningh/nh/astro-dra-ui-5002` |
| Git分支 | `main` | `work/ui-5002-20261028` |
| 当前HEAD | `e9be103` | `e9be103`，新增功能尚在未提交工作区 |
| Compose项目 | `local_deep_research` | `astro-dra-test-5002` |
| 应用容器 | `local_deep_research-local-deep-research-1` | `astro-dra-test-5002-local-deep-research-1` |
| 当前镜像 | `astro-dra:main-20261028` | `astro-dra:accounts-5002-20261102` |
| Compose入口 | 主工作区下 `local_deep_research/docker-compose.yml` 和 `compose.production.local.yml` | **主工作区**下 `compose.yaml`，环境文件为 `.env.test-5002` |
| 应用数据卷 | `local_deep_research_ldr_data` | `astro-dra-test-5002_ldr_data` |
| 配置卷 | 原匿名配置卷 | `astro-dra-test-5002_ldr_config` |

两个目录是同一仓库的Git worktree，共享提交和分支信息，文件改动互相独立。两端数据卷独立；5000另有原脚本卷及用户日志挂载。

**代码开发目录与5002的运行配置目录不同。** 5002镜像内已包含UI分支的功能，但容器标签记录的Compose工作目录仍为主工作区。后续构建应明确使用开发工作区的build context；部署时沿用既有5002项目、环境文件和数据卷。不能直接在主工作区执行通用build，假定会包含UI工作区的新增代码，也不能在开发目录无参数执行up，意外创建另一组卷或服务。

`/data/ningh/nh`本身不是Git仓库；同级 `local-deep-research/`、`local_deep_research/`、`ldr_ori/`、`ldr-official-lab/`、实验与备份目录不是当前5002的默认开发入口。另有5001及多个对照实例，后续操作按Compose项目和容器精确定位。

## 源码与构建边界

运行应用是Python Flask/Jinja及原生JS前端，研究任务在后台线程执行，使用LangChain/LangGraph工具编排；账号认证库与各用户SQLCipher加密数据库分别承担身份和研究数据存储。这里描述的是当前固定运行镜像与部署补丁，旁置上游快照可能具有不同接口。

| 路径（相对开发工作区） | 作用 |
| --- | --- |
| `local_deep_research/research_service.py` | 后台任务、普通/详细模式协调、保存与导出入口 |
| `local_deep_research/langgraph_agent_strategy.py` | Agent工具、来源收集、子任务及最终综合 |
| `local_deep_research/search_engine_pubmed.py`、`overlay/search_engine_europepmc.py` | 生物医学检索、摘要和文献元数据 |
| `local_deep_research/research_verify/` | 来源身份、去重与版本关系、材料构建、写后核对、引用映射和私有trace；也保留旧CLI/兼容模块，并非全部启用 |
| `local_deep_research/overlay/` | 固定运行镜像的引用处理器、抓取、详细报告、存储及装配等补丁 |
| `local_deep_research/overlay/ui/` | 实际Flask模板、工作台样式/交互、中文词典、三主题和角色界面 |
| `local_deep_research/astro_accounts/` | 角色与审批存储、请求访问控制、普通用户服务配置策略及root初始化CLI |
| `deployment/overlay-manifest.json` | 当前53个应用覆盖目标；`research_verify`另行整包安装 |
| `deployment/install_accounts.py` | 独立安装账号包，向7个原生文件安装位置检查钩子 |
| `deployment/Dockerfile` | 固定上游digest，完整安装后端、UI及账号补丁 |
| `deployment/Dockerfile.ui`、`Dockerfile.accounts` | 在指定既有镜像上分层安装；使用时核对基础镜像，避免丢失其他功能 |
| `local-deep-research/` | 旁置上游源码快照，修改不会自动进入根Dockerfile构建 |
| `scripts/`、`local_deep_research/tests/` | 离线回归、隔离浏览器/运行验证及联网诊断入口 |

完整补丁安装时还会向Agent追加 `COLLECTION_HOOK`；账号安装器会进一步修改调度器等文件。对比源码与包内哈希时要计入安装转换。

## 当前研究数据流

1. 用户提交研究问题和普通/详细模式；后端校验身份、角色及参数，读取设置快照并启动后台任务。普通用户使用服务端默认值和环境配置，管理员保留高级配置能力。
2. 默认LangGraph Agent按需调用PubMed、SearXNG、Europe PMC，做相关性筛选与来源收集。默认web_search仍连接SearXNG；三源可用不表示每个任务必定查询三源。5002的SearXNG配置收敛到Bing。
3. 来源按可靠标识去重，保留完整摘要、可取得的原文、书目信息与版本关系；抓取路径保全实际材料。自动PubMed全文默认关闭，按需补取路径保留。
4. citation handler调用 `research_verify/evidence_flow.py`：文献身份/版本补全、必要引用来源预留、材料预算与分批选材、writer成文。草稿用于组织，不能替代论文证据。
5. 开启事实检查时，对writer实际产出进行带章节/段落/表格上下文的核对，有限补证；可定位原文及独立确认后才局部修订。未决或检查失败不阻断报告，也不等同通过。
6. 普通报告经research_service、详细报告经report_generator进入 `publish_report`，统一引用首次出现顺序、同篇书目及链接，保留原编号和metadata，再保存、装配展示和导出。
7. `/data/research_traces`按任务记录实际材料、writer、核对及publication过程。trace是私有诊断资料，不附加到报告正文。

当前部署默认模型均为 `openai_endpoint / deepseek-v4-flash`；候选来源预算500，每次检索参数12候选/6筛后。原生事实检查开启，保存前独立逐引用QC关闭，私有trace开启。不能混淆写后事实核对与保存前QC开关；不自行恢复旧强制准入、规则删句或题目专用筛选。

## 5002相对main的待整理工作

10月28日的检索、证据连续性与引用修复已通过PR #2进入main并同步5000。此后5002新增工作台、浅/深/跟随系统主题、中文界面、侧栏、普通用户/管理员/root角色与审批、普通用户配置控制。代理relay的UID/GID参数化等部署改动在两个工作区也有未提交内容。

当前两个工作区都有已有改动与未跟踪文件。UI分支HEAD与main相同不表示功能相同；直接合并该分支目前不会带入尚未提交的功能。后续合入前应核对完整diff及新增文件，保留主工作区已有README/部署记录等改动，排除私有环境文件、账号数据、日志及实验凭据。

已知限制：闲置后随机重新登录尚未完整定位；内存会话重启丢失、remember期限与数据库凭据期限不衔接已有隔离证据。检索长尾稳定性、引用语义漏判、全文可得性、JIF与纳入条件核实也没有全面解决。详见登录诊断、账号角色说明和最近证据流程记录，勿把旧计划当成现行开发要求。

## 本轮验证与后续开发方式

- 两实例容器均healthy；`/auth/login`均HTTP200，5002加载工作台资源。
- 5002包内53个manifest目标、29个research_verify模块、5个astro_accounts模块，共87文件，与开发工作区计入安装转换后的内容全部一致。本次未逐一哈希验收其余原生账号钩子文件。
- 离线模块回归403 passed（4.10秒）；`node scripts/check_model_selection.cjs`通过。
- 命令行 `git fetch --prune origin`因缺少HTTPS认证失败；通过已连接GitHub的只读compare接口确认远程main与 `e9be10309214dcad54e036663c04534cf52c9337` identical、ahead/behind均0。未修改远程引用。
- 未创建研究或测试账号，没有调用真实研究模型、运行联网检索或重新验收研究质量；没有构建/重启/部署。

在开发工作区执行离线基线：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=local_deep_research /data/ningh/nh/verify-venv/bin/python -m pytest -q -p no:cacheprovider local_deep_research/tests
node scripts/check_model_selection.cjs
```

后续按需求修改实际部署补丁，在隔离环境验证对应界面/权限或研究链路，再构建独立版本标签并仅更新5002应用。部署前检查活跃任务、记录镜像/环境/卷并按改动备份。复用既有5002卷，不与5000共享或相互覆盖。

5002测试完成后整理并提交功能，合入main；更新5000还需单独使用其原Compose项目及两份配置、原数据卷和模型连接。Git合并与5000服务更新是两个步骤，具体操作在相应任务中执行。本轮不触发这两个步骤。

相关记录：[源码布局](source-layout.md)、[5000部署](deploy-main-5000-20261028.md)、[账号角色](account-roles-5002-20261102.md)、[登录诊断](auth-session-diagnosis-20261030.md)、[写后核对](review-repairs-model-comparison-20261027.md)。
