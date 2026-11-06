# 开发文档与记录完整目录

整理日期：2026-11-04。[总索引](README.md) · [当前状态](current-status.md) · [待办](roadmap.md) · [整理核查](documentation-audit-20261104.md)。

覆盖开发工作区docs下全部Markdown、JSON和PNG，并补入main独有的5000部署记录。保持原文件名和原结果；表中状态区分当时事件与当前能力，详细断言以正文/证据为准。

本集合：**78份Markdown、116份JSON、9张截图，共203个文件**。仓库相邻文档、构建清单及私有资料另列，不包含上游快照的全部文档。

## 当前入口与维护说明

| 文件 | 对应什么 | 如何理解 |
| --- | --- | --- |
| [README.md](README.md) | 文档总入口、按问题找资料、功能对应及维护规则 | 当前入口 |
| [current-status.md](current-status.md) | 两实例、已实现能力、开关及验证边界 | 当前事实汇总 |
| [roadmap.md](roadmap.md) | 有效待办、已有进展、完成标准及候选方向 | 当前待办；未自动开始实施 |
| [development-progress.md](development-progress.md) | 最近会话变化、接续步骤与历史入口 | 短接续；不再承载全部旧流水 |
| [current-research-flow-20261016.md](current-research-flow-20261016.md) | 当前提问→检索→成文→核对→保存导出 | 当前说明；旧文件名保留 |
| [source-layout.md](source-layout.md) | 部署补丁、上游快照、53覆盖目标和账号钩子 | 当前开发边界 |
| [deployment.md](deployment.md) | 本机5002构建与更新、main/5000发布及回退 | 当前操作说明 |
| [test-instance-5002.md](test-instance-5002.md) | 5002项目、容器、环境文件、卷与只读入口 | 当前实例说明 |
| [deploy-main-5000-20261106.json](deploy-main-5000-20261106.json) | main功能提交、5000镜像/用户/备份/验证结果 | 已部署；不含密码或用户材料 |
| [deploy-main-5000-20261106.md](deploy-main-5000-20261106.md) | 合入main、GitHub提交、5000切换与普通用户迁移 | 部署状态以正文和后续实测为准 |
| [5002-vs-5000-20261106.md](5002-vs-5000-20261106.md) | 当前两运行实例累计功能、配置、工程和未完成边界 | 11月6日只读核对；不沿用合并前差异 |
| [5002-vs-5000-20261106.json](5002-vs-5000-20261106.json) | 31修改/16新增完整路径和SHA、AST及配置对照 | 限三安装包代码/模板/资源；非镜像全盘差异 |
| [document-catalog.md](document-catalog.md) | 本集合全部MD、JSON、截图逐文件归属 | 本文件；完整目录 |
| [documentation-audit-20261104.md](documentation-audit-20261104.md) | 整理范围、快照、校验及旧链接限制 | 本轮文档整理记录 |

## 接续基线与原始长文快照

| 文件 | 对应什么 | 如何理解 |
| --- | --- | --- |
| [project-overview-20261104.md](project-overview-20261104.md) | 初次熟悉项目的目录、架构及当日基线 | 2026-11-04快照；后续看current-status |
| [development-progress-history-20261104.md](development-progress-history-20261104.md) | 整理前原文快照：development-progress.md（astro-dra-ui-5002） | 逐字节保留；当时版本，不能照搬旧下一步/镜像 |
| [research-flow-history-20261104.md](research-flow-history-20261104.md) | 整理前原文快照：current-research-flow-20261016.md（astro-dra-ui-5002） | 逐字节保留；当时版本，不能照搬旧下一步/镜像 |
| [deployment-history-20261104.md](deployment-history-20261104.md) | 整理前原文快照：deployment.md（astro-dra-ui-5002） | 逐字节保留；当时版本，不能照搬旧下一步/镜像 |
| [test-instance-5002-history-20261104.md](test-instance-5002-history-20261104.md) | 整理前原文快照：test-instance-5002.md（astro-dra-ui-5002） | 逐字节保留；当时版本，不能照搬旧下一步/镜像 |
| [source-layout-history-20261104.md](source-layout-history-20261104.md) | 整理前原文快照：source-layout.md（astro-dra-ui-5002） | 逐字节保留；当时版本，不能照搬旧下一步/镜像 |
| [development-progress-main-history-20261104.md](development-progress-main-history-20261104.md) | 整理前原文快照：development-progress.md（astro-dra） | 逐字节保留；当时版本，不能照搬旧下一步/镜像 |
| [research-flow-main-history-20261104.md](research-flow-main-history-20261104.md) | 整理前原文快照：current-research-flow-20261016.md（astro-dra） | 逐字节保留；当时版本，不能照搬旧下一步/镜像 |

## 检索、来源与证据流程

| 文件 | 对应什么 | 如何理解 |
| --- | --- | --- |
| [lrrc4-direction-diagnosis-20261104.md](lrrc4-direction-diagnosis-20261104.md) | 子专题主体/机制反转传播、核对漏判与5次隔离模型试验 | 诊断和候选验证；未修改后端或部署修复 |
| [subtask-handoff-20261104.md](subtask-handoff-20261104.md) | 子任务研究梳理、原文材料和出处交付第一版 | 已部署5002；本轮核查未改，非准确率验收 |
| [subtask-handoff-deploy-5002-20261104.json](subtask-handoff-deploy-5002-20261104.json) | 5002子任务交付版本部署/重启、安装SHA及环境/卷/其他服务检查 | 部署证据；非完整研究质量验收 |
| [subtask-handoff-live-4926df11-20261104.md](subtask-handoff-live-4926df11-20261104.md) | 部署后真实任务过程与作用方向反转复现 | 问题未解决；3子任务未到交付，主写作/核查仍有错 |
| [subtask-handoff-live-4926df11-20261104.json](subtask-handoff-live-4926df11-20261104.json) | 同任务阶段数量、失败及最终错误的结构化结果 | 只读实跑观察，非修复验收 |
| [subtask-handoff-v2-20261104.md](subtask-handoff-v2-20261104.md) | 有界检索、独立交付、按子任务保全材料及逐步记录 | 11月4日优化测试，后续11月5日已部署；核查未改，非总体准确率验收 |
| [subtask-handoff-v2-20261104.json](subtask-handoff-v2-20261104.json) | 最终回归、安装图执行及隔离新检索/原文回放结果 | 明确两测试镜像范围、失败与语义未覆盖边界 |
| [subtask-handoff-live-62827275-20261105.md](subtask-handoff-live-62827275-20261105.md) | 11月5日用户任务全程观察，子任务失败与LRRC4正确表述 | 仍运行第一版；不作为第二版生效或总体准确性证明 |
| [subtask-handoff-live-62827275-20261105.json](subtask-handoff-live-62827275-20261105.json) | 该任务数量、退出、原文供给、核查及运行版本 | 100条快照校验，旧版异常内部记录仍缺失 |
| [subtask-handoff-v2-deploy-5002-20261105.md](subtask-handoff-v2-deploy-5002-20261105.md) | 第二版部署、实际安装、服务检查、备份及回退 | 已部署重启5002；未新跑研究或合入main |
| [subtask-handoff-v2-deploy-5002-20261105.json](subtask-handoff-v2-deploy-5002-20261105.json) | 镜像/容器、安装SHA、HTTP及配置/其他服务不变证据 | 部署验证，非总体语义质量验收 |
| [subtask-handoff-live-0fee90a3-20261105.md](subtask-handoff-live-0fee90a3-20261105.md) | 第二版首轮真实任务交付/原文/成文/核查对照，正文选段数据回放 | 收尾生效，仍有总结、材料传递和核查问题；只读未修复 |
| [subtask-handoff-live-0fee90a3-20261105.json](subtask-handoff-live-0fee90a3-20261105.json) | 179快照、34卡、3子任务、LRRC4及三个剩余问题的结构化证据 | 过程与有限语义复查，非全篇独立审计或准确率证明 |
| [subtask-scope-v3-20261105.md](subtask-scope-v3-20261105.md) | 第三版选段、问题导航、阅读范围和写作前主体分组，含失败方案 | 已实现测试，随后部署5002；核查未改，有限样本不当语义全部解决 |
| [subtask-scope-v3-20261105.json](subtask-scope-v3-20261105.json) | 465回归、冻结作业回放、安装和真实模型两轮读写结果 | 引句/主体存在不等于语义核验，新增模型读取时延需观察 |
| [subtask-scope-v3-deploy-5002-20261105.md](subtask-scope-v3-deploy-5002-20261105.md) | 第三版同镜像部署、重启、原卷保留和实际测试 | 新检索完成；空子任务和部分核查未执行，非质量全部验收 |
| [subtask-scope-v3-deploy-5002-20261105.json](subtask-scope-v3-deploy-5002-20261105.json) | 安装SHA、HTTP/环境对比和真实过程统计 | 不含凭据、原报告或用户数据库 |
| [search-stability-20261016.md](search-stability-20261016.md) | 代理稳定性与当时限流来源暂停 | 阶段部署记录；来源池后续已收敛三源 |
| [search-engine-audit-20261019.md](search-engine-audit-20261019.md) | 29类安装引擎及SearXNG后端探测、失败分类 | 当时审计；不是当前所有引擎健康证明 |
| [search-recovery-20261020.md](search-recovery-20261020.md) | 三源恢复、查询/相关性、摘要和共享节流 | 演进记录；后续进入main/5000 |
| [runtime-fixes-20261021.md](runtime-fixes-20261021.md) | QC关/原生检查开、PMC自身身份及相关性解析 | 演进记录；当时200来源，现为500 |
| [abstract-context-20261021.md](abstract-context-20261021.md) | 500来源、完整摘要、分批选材和Europe PMC正文路由 | 已实现并进入main；全文/选文质量有限制 |
| [citation-grounding-20261019.md](citation-grounding-20261019.md) | 抓取材料保全、来源信息和写作证据提示 | 实现记录；文中未部署为当时时点，后续已集成 |
| [generic-source-repairs-20261026.md](generic-source-repairs-20261026.md) | XML语义、稳定身份、关系保留及工具返回trace | 已集成main；文中写前检查随后被替换 |
| [synthesis-trace-20261026.md](synthesis-trace-20261026.md) | 私有过程快照与当时检查输入优化 | 阶段记录；工具返回缺口在后续来源修复补齐 |
| [evidence-flow-20261027.md](evidence-flow-20261027.md) | 必要证据预留、版本补取、写后核对及有限修订 | 工程已集成main；不代表语义全部通过 |
| [review-repairs-model-comparison-20261027.md](review-repairs-model-comparison-20261027.md) | 核对编排、PMC身份桥及双模型冻结/聚焦比较 | 最近后端实现与限制；不同试验版本不得混用 |

## 5002界面与账号

| 文件 | 对应什么 | 如何理解 |
| --- | --- | --- |
| [ui-workspace-20261028.md](ui-workspace-20261028.md) | 工作台、报告目录、专注阅读、登录与移动端 | 已部署5002；未合入main |
| [ui-chinese-20261030.md](ui-chinese-20261030.md) | 中文词典、显示层翻译及用户内容保护 | 已部署5002；未合入main |
| [sidebar-5002-20261030.md](sidebar-5002-20261030.md) | 侧栏收起、用户偏好、手机抽屉与底部简化 | 已部署5002；未合入main |
| [account-roles-5002-20261102.md](account-roles-5002-20261102.md) | 普通用户/管理员/root、审批和服务端配置控制 | 已部署5002；未合入main；登录问题未修 |

## 生产部署与模型变更

| 文件 | 对应什么 | 如何理解 |
| --- | --- | --- |
| [deploy-main-5000-20261028.md](deploy-main-5000-20261028.md) | main同步5000、原卷/账号保留、备份与回退 | 已执行的生产事件；从main工作区补入 |
| [azure-gpt56-deploy-5002-20261026.md](azure-gpt56-deploy-5002-20261026.md) | 临时Azure模型接入、兼容验证与切换 | 历史切换；不是当前默认 |
| [deepseek-flash-stage-5002-20261026.md](deepseek-flash-stage-5002-20261026.md) | 官方DeepSeek连接准备与隔离验证 | 当时仅准备；不表示当前默认或可用性 |
| [deepseek-key-rotate-5002-20261026.md](deepseek-key-rotate-5002-20261026.md) | 私有密钥轮换和加载验证 | 历史操作摘要；凭据不在文档集合 |
| [deepseek-default-5002-20261026.md](deepseek-default-5002-20261026.md) | 当时默认切到官方Flash | 已被10月27日恢复原V4替代 |
| [restore-deepseek-v4-20261027.md](restore-deepseek-v4-20261027.md) | 恢复原OpenAI兼容deepseek-v4-flash | 恢复事件；当前模型以current-status为准 |

## 诊断、观察与真实流程试跑

| 文件 | 对应什么 | 如何理解 |
| --- | --- | --- |
| [auth-session-diagnosis-20261030.md](auth-session-diagnosis-20261030.md) | remember、内存SID、凭据期限及随机失效诊断 | 仅诊断；登录持久性未修复 |
| [search-connectivity-20261028.md](search-connectivity-20261028.md) | 三源断连、relay UID差异及连接修复 | 主要断连已修；零命中/失败提示待做 |
| [citation-case-diagnosis-20261026.md](citation-case-diagnosis-20261026.md) | IMC/4i、肾脏数量及分析输入错配溯源 | 当时错例；不等于后续全部修复 |
| [citation-consistency-plan-20261021.md](citation-consistency-plan-20261021.md) | 同文重复、版本与分析归属的原始诊断方案 | 部分后续已实现；写前检查描述已过期 |
| [kidney-count-review-20261027.md](kidney-count-review-20261027.md) | 肾样本与动物数误写、证据及模型责任定位 | 诊断；未以单题规则修复 |
| [report-e398fd15-review-20261027.md](report-e398fd15-review-20261027.md) | 五类生成/版本/材料问题逐项定位 | 具体报告诊断；后续工程另有记录 |
| [test001-review-20261027.md](test001-review-20261027.md) | 报告与319快照对账、纳入条件与新核对缺陷 | 具体报告诊断；部分编排/身份问题随后修复 |
| [trace-review-7162eae1-20261026.md](trace-review-7162eae1-20261026.md) | 六组引用/单位/勘误问题沿实际材料链追踪 | 诊断；后续来源修复与写后核对处理部分缺口 |
| [live-stall-5002-20261026.md](live-stall-5002-20261026.md) | 网页任务长等待阶段与外部调用观察 | 观察记录；不是长等待已修声明 |
| [log-triage-20261016.md](log-triage-20261016.md) | 日志故障分级、限流/解析/依赖排查 | 历史诊断；严格门槛及旧来源建议已失效 |
| [web-run-log-review-20261021.md](web-run-log-review-20261021.md) | 网页任务06641267观察、PMC错映射与解析/截断 | 当时缺陷；后续runtime/abstract修复部分问题 |
| [web-run-log-review-20261021-7759b63e.md](web-run-log-review-20261021-7759b63e.md) | 网页任务7759b63e观察、来源容量/取文/长等待 | 当时阶段；不等于当前5002参数 |
| [spatial-research-diagnostic-20261019.md](spatial-research-diagnostic-20261019.md) | 默认安装版第一轮完整研究及失败诊断 | 历史真实实跑；研究目标失败 |
| [spatial-research-repeat-20261020.md](spatial-research-repeat-20261020.md) | 同镜像同题第二轮、召回与限流原因确认 | 历史真实实跑；目标未完整达成 |
| [spatial-research-search-patched-20261020.md](spatial-research-search-patched-20261020.md) | 只替换检索补丁的第三轮完整流程 | 历史实跑；不能代表最终全部补丁 |
| [spatial-research-collection-patched-20261020.md](spatial-research-collection-patched-20261020.md) | 定向collector补丁的第四轮及writer字段缺口 | 历史实跑；不是当前完整版本质量验收 |

## 历史差异比较

| 文件 | 对应什么 | 如何理解 |
| --- | --- | --- |
| [5000-vs-5002-20261026.md](5000-vs-5002-20261026.md) | 10月26日两实例安装版差异 | 过往比较；此后后端合并/5000更新已发生 |
| [5002-vs-main-20261028.md](5002-vs-main-20261028.md) | 10月28日合并前累计后端变化 | 合并前比较；不等于现在5002与main差异 |

## 历史严格核验阶段

| 文件 | 对应什么 | 如何理解 |
| --- | --- | --- |
| [verification-20261012.md](verification-20261012.md) | 早期部署整理与55项测试、固定镜像检查 | 历史工程基线；不是当前测试数量 |
| [verification-foundation-20261012.md](verification-foundation-20261012.md) | M0契约、样本、出口审计和基础验证 | 历史基础，非当前功能已全部验收 |
| [ldr-verification-engineering-plan.md](ldr-verification-engineering-plan.md) | 旧M0/M1/M2/M3/M4严格准入路线 | 历史方案；10月16日方向撤回，不作为待办 |
| [claim-evidence-step1-20261012.md](claim-evidence-step1-20261012.md) | 旧M3-A逐引用映射及原文短引定位 | 历史实现阶段；后续流程/契约已调整 |
| [claim-evidence-step2-20261012.md](claim-evidence-step2-20261012.md) | 旧M3-A相关片段及无引用候选检测 | 历史实现阶段；不表示当前自动开启审计 |
| [claim-evidence-step3-20261014.md](claim-evidence-step3-20261014.md) | 旧六维语义核查及真实小样本比较 | 历史试验；六维强制结构不再作为门槛 |
| [claim-evidence-step4-20261014.md](claim-evidence-step4-20261014.md) | 旧结论修订/删除/隔离循环 | 旧规则循环已撤回；区别于当前写后有限修订 |
| [claim-evidence-step5-20261016.md](claim-evidence-step5-20261016.md) | 旧统一发布控制与核验状态契约 | 旧强制发布控制已撤回，现统一映射保留 |
| [claim-evidence-step6-20261016.md](claim-evidence-step6-20261016.md) | 旧严格报告与全部出口验收过程 | 未全面通过；不能续用旧待办或accepted标签 |
| [semantic-pilot-20261014.md](semantic-pilot-20261014.md) | 早期语义小样本、正反例与迭代结果 | 历史小样本；非独立准确率验收 |

## 未采用的提示试验

| 文件 | 对应什么 | 如何理解 |
| --- | --- | --- |
| [count-scope-prompt-trial-20261027.md](count-scope-prompt-trial-20261027.md) | 两版数量对象通用提示对照及撤回原因 | 试验未达目标、已撤回、未部署 |

## 结构化结果：逐文件对应

同名MD仅是常见惯例，下表给出每份JSON的实际归属。原始失败、旧版结果和后续复核全部保留；没有统一用“最后一次”替代不同范围。

| JSON文件 | 对应说明 | 用途与边界 |
| --- | --- | --- |
| [5000-vs-5002-20261026.json](5000-vs-5002-20261026.json) | [5000-vs-5002-20261026.md](5000-vs-5002-20261026.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [5002-vs-main-20261028.json](5002-vs-main-20261028.json) | [5002-vs-main-20261028.md](5002-vs-main-20261028.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [abstract-context-20261021.json](abstract-context-20261021.json) | [abstract-context-20261021.md](abstract-context-20261021.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [account-roles-5002-20261102.json](account-roles-5002-20261102.json) | [account-roles-5002-20261102.md](account-roles-5002-20261102.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [advisory-deploy-5002-20261016.json](advisory-deploy-5002-20261016.json) | [research-flow-history-20261104.md](research-flow-history-20261104.md) | 10月16日取消强制发布门槛后部署记录 |
| [azure-gpt56-deploy-5002-20261026.json](azure-gpt56-deploy-5002-20261026.json) | [azure-gpt56-deploy-5002-20261026.md](azure-gpt56-deploy-5002-20261026.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [biomedical-sources-20261016.json](biomedical-sources-20261016.json) | [research-flow-history-20261104.md](research-flow-history-20261104.md) | 当时两源收敛结果；后续已增Europe PMC为三源 |
| [citation-case-diagnosis-20261026.json](citation-case-diagnosis-20261026.json) | [citation-case-diagnosis-20261026.md](citation-case-diagnosis-20261026.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [citation-consistency-plan-20261021.json](citation-consistency-plan-20261021.json) | [citation-consistency-plan-20261021.md](citation-consistency-plan-20261021.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [citation-display-20261016-final.json](citation-display-20261016-final.json) | [research-flow-history-20261104.md](research-flow-history-20261104.md) | 引用方括号、顺序和书目修复/部署的阶段结果 |
| [citation-display-20261016.json](citation-display-20261016.json) | [research-flow-history-20261104.md](research-flow-history-20261104.md) | 引用方括号、顺序和书目修复/部署的阶段结果 |
| [citation-display-deploy-20261016.json](citation-display-deploy-20261016.json) | [research-flow-history-20261104.md](research-flow-history-20261104.md) | 引用方括号、顺序和书目修复/部署的阶段结果 |
| [citation-grounding-comparison-20261019-final.json](citation-grounding-comparison-20261019-final.json) | [citation-grounding-20261019.md](citation-grounding-20261019.md) | 材料与生成受控/真实流程/模型评审，保留失败轮次 |
| [citation-grounding-comparison-20261019-review2.json](citation-grounding-comparison-20261019-review2.json) | [citation-grounding-20261019.md](citation-grounding-20261019.md) | 材料与生成受控/真实流程/模型评审，保留失败轮次 |
| [citation-grounding-comparison-20261019.json](citation-grounding-comparison-20261019.json) | [citation-grounding-20261019.md](citation-grounding-20261019.md) | 材料与生成受控/真实流程/模型评审，保留失败轮次 |
| [citation-grounding-e2e-20261019-final.json](citation-grounding-e2e-20261019-final.json) | [citation-grounding-20261019.md](citation-grounding-20261019.md) | 材料与生成受控/真实流程/模型评审，保留失败轮次 |
| [citation-grounding-e2e-20261019.json](citation-grounding-e2e-20261019.json) | [citation-grounding-20261019.md](citation-grounding-20261019.md) | 材料与生成受控/真实流程/模型评审，保留失败轮次 |
| [claim-revision-pilot-20261014-audit-final.json](claim-revision-pilot-20261014-audit-final.json) | [claim-evidence-step4-20261014.md](claim-evidence-step4-20261014.md) | 旧修订循环试跑，后续严格规则路径撤回 |
| [claim-revision-pilot-20261014-final.json](claim-revision-pilot-20261014-final.json) | [claim-evidence-step4-20261014.md](claim-evidence-step4-20261014.md) | 旧修订循环试跑，后续严格规则路径撤回 |
| [claim-revision-pilot-20261014-scope-final.json](claim-revision-pilot-20261014-scope-final.json) | [claim-evidence-step4-20261014.md](claim-evidence-step4-20261014.md) | 旧修订循环试跑，后续严格规则路径撤回 |
| [claim-revision-pilot-20261014.json](claim-revision-pilot-20261014.json) | [claim-evidence-step4-20261014.md](claim-evidence-step4-20261014.md) | 旧修订循环试跑，后续严格规则路径撤回 |
| [count-scope-prompt-trial-20261027.json](count-scope-prompt-trial-20261027.json) | [count-scope-prompt-trial-20261027.md](count-scope-prompt-trial-20261027.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [deepseek-default-5002-20261026.json](deepseek-default-5002-20261026.json) | [deepseek-default-5002-20261026.md](deepseek-default-5002-20261026.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [deepseek-flash-stage-5002-20261026.json](deepseek-flash-stage-5002-20261026.json) | [deepseek-flash-stage-5002-20261026.md](deepseek-flash-stage-5002-20261026.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [deepseek-key-rotate-5002-20261026.json](deepseek-key-rotate-5002-20261026.json) | [deepseek-key-rotate-5002-20261026.md](deepseek-key-rotate-5002-20261026.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [deploy-main-5000-20261028.json](deploy-main-5000-20261028.json) | [deploy-main-5000-20261028.md](deploy-main-5000-20261028.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [documentation-audit-20261104.json](documentation-audit-20261104.json) | [documentation-audit-20261104.md](documentation-audit-20261104.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [evidence-flow-20261027.json](evidence-flow-20261027.json) | [evidence-flow-20261027.md](evidence-flow-20261027.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [generic-source-repairs-20261026.json](generic-source-repairs-20261026.json) | [generic-source-repairs-20261026.md](generic-source-repairs-20261026.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [kidney-count-review-20261027.json](kidney-count-review-20261027.json) | [kidney-count-review-20261027.md](kidney-count-review-20261027.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [live-stall-5002-20261026.json](live-stall-5002-20261026.json) | [live-stall-5002-20261026.md](live-stall-5002-20261026.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [log-observation-20261016.json](log-observation-20261016.json) | [log-triage-20261016.md](log-triage-20261016.md) | 两分钟日志观察原始分类，含后续需澄清的误判 |
| [proxy-check-20261016.json](proxy-check-20261016.json) | [search-stability-20261016.md](search-stability-20261016.md) | 当时9876代理路径检查 |
| [publication-e2e-20261014-attempt2.json](publication-e2e-20261014-attempt2.json) | [claim-evidence-step6-20261016.md](claim-evidence-step6-20261016.md) | 旧严格发布/存储出口试验；final/accepted不表示当前质量通过 |
| [publication-e2e-20261014-attempt3.json](publication-e2e-20261014-attempt3.json) | [claim-evidence-step6-20261016.md](claim-evidence-step6-20261016.md) | 旧严格发布/存储出口试验；final/accepted不表示当前质量通过 |
| [publication-e2e-20261014-attempt4.json](publication-e2e-20261014-attempt4.json) | [claim-evidence-step6-20261016.md](claim-evidence-step6-20261016.md) | 旧严格发布/存储出口试验；final/accepted不表示当前质量通过 |
| [publication-e2e-20261014-diagnostic.json](publication-e2e-20261014-diagnostic.json) | [claim-evidence-step6-20261016.md](claim-evidence-step6-20261016.md) | 旧严格发布/存储出口试验；final/accepted不表示当前质量通过 |
| [publication-e2e-20261014-final.json](publication-e2e-20261014-final.json) | [claim-evidence-step6-20261016.md](claim-evidence-step6-20261016.md) | 旧严格发布/存储出口试验；final/accepted不表示当前质量通过 |
| [publication-e2e-20261014-scoped-diagnostic.json](publication-e2e-20261014-scoped-diagnostic.json) | [claim-evidence-step6-20261016.md](claim-evidence-step6-20261016.md) | 旧严格发布/存储出口试验；final/accepted不表示当前质量通过 |
| [publication-e2e-20261014-scoped.json](publication-e2e-20261014-scoped.json) | [claim-evidence-step6-20261016.md](claim-evidence-step6-20261016.md) | 旧严格发布/存储出口试验；final/accepted不表示当前质量通过 |
| [publication-e2e-20261016-accepted.json](publication-e2e-20261016-accepted.json) | [claim-evidence-step6-20261016.md](claim-evidence-step6-20261016.md) | 旧严格发布/存储出口试验；final/accepted不表示当前质量通过 |
| [publication-e2e-20261016-frozen-final.json](publication-e2e-20261016-frozen-final.json) | [claim-evidence-step6-20261016.md](claim-evidence-step6-20261016.md) | 旧严格发布/存储出口试验；final/accepted不表示当前质量通过 |
| [publication-e2e-20261016-live-final.json](publication-e2e-20261016-live-final.json) | [claim-evidence-step6-20261016.md](claim-evidence-step6-20261016.md) | 旧严格发布/存储出口试验；final/accepted不表示当前质量通过 |
| [publication-e2e-20261016-reviewed-final.json](publication-e2e-20261016-reviewed-final.json) | [claim-evidence-step6-20261016.md](claim-evidence-step6-20261016.md) | 旧严格发布/存储出口试验；final/accepted不表示当前质量通过 |
| [publication-e2e-20261016-scoped.json](publication-e2e-20261016-scoped.json) | [claim-evidence-step6-20261016.md](claim-evidence-step6-20261016.md) | 旧严格发布/存储出口试验；final/accepted不表示当前质量通过 |
| [publication-e2e-20261016-subset-final.json](publication-e2e-20261016-subset-final.json) | [claim-evidence-step6-20261016.md](claim-evidence-step6-20261016.md) | 旧严格发布/存储出口试验；final/accepted不表示当前质量通过 |
| [publication-e2e-20261016-v2-final.json](publication-e2e-20261016-v2-final.json) | [claim-evidence-step6-20261016.md](claim-evidence-step6-20261016.md) | 旧严格发布/存储出口试验；final/accepted不表示当前质量通过 |
| [publication-e2e-review-20261016-first.json](publication-e2e-review-20261016-first.json) | [claim-evidence-step6-20261016.md](claim-evidence-step6-20261016.md) | 旧publication结果逐项复核；保留自动检查与复核差异 |
| [publication-e2e-review-20261016-live-final.json](publication-e2e-review-20261016-live-final.json) | [claim-evidence-step6-20261016.md](claim-evidence-step6-20261016.md) | 旧publication结果逐项复核；保留自动检查与复核差异 |
| [publication-e2e-review-20261016-second.json](publication-e2e-review-20261016-second.json) | [claim-evidence-step6-20261016.md](claim-evidence-step6-20261016.md) | 旧publication结果逐项复核；保留自动检查与复核差异 |
| [publication-e2e-review-20261016-third.json](publication-e2e-review-20261016-third.json) | [claim-evidence-step6-20261016.md](claim-evidence-step6-20261016.md) | 旧publication结果逐项复核；保留自动检查与复核差异 |
| [pubmed-auto-fulltext-diagnosis-20261026.json](pubmed-auto-fulltext-diagnosis-20261026.json) | [project-overview-20261104.md](project-overview-20261104.md) | PubMed自动全文开关/失败保留摘要诊断；不代表开启自动全文 |
| [qwen-flash-deploy-5002-20261016.json](qwen-flash-deploy-5002-20261016.json) | [test-instance-5002-history-20261104.md](test-instance-5002-history-20261104.md) | 当时Qwen接入、模型发现/流式/工具烟测及部署 |
| [qwen-flash-smoke-20261016.json](qwen-flash-smoke-20261016.json) | [test-instance-5002-history-20261104.md](test-instance-5002-history-20261104.md) | 当时Qwen接入、模型发现/流式/工具烟测及部署 |
| [report-e398fd15-review-20261027.json](report-e398fd15-review-20261027.json) | [report-e398fd15-review-20261027.md](report-e398fd15-review-20261027.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [report-preservation-e2e-20261016-fourth.json](report-preservation-e2e-20261016-fourth.json) | [research-flow-history-20261104.md](research-flow-history-20261104.md) | 撤除强制门槛后的保留输出试验；早期失败与第四轮分别保留 |
| [report-preservation-e2e-20261016-second.json](report-preservation-e2e-20261016-second.json) | [research-flow-history-20261104.md](research-flow-history-20261104.md) | 撤除强制门槛后的保留输出试验；早期失败与第四轮分别保留 |
| [report-preservation-e2e-20261016-third.json](report-preservation-e2e-20261016-third.json) | [research-flow-history-20261104.md](research-flow-history-20261104.md) | 撤除强制门槛后的保留输出试验；早期失败与第四轮分别保留 |
| [report-preservation-e2e-20261016.json](report-preservation-e2e-20261016.json) | [research-flow-history-20261104.md](research-flow-history-20261104.md) | 撤除强制门槛后的保留输出试验；早期失败与第四轮分别保留 |
| [restore-deepseek-v4-20261027.json](restore-deepseek-v4-20261027.json) | [restore-deepseek-v4-20261027.md](restore-deepseek-v4-20261027.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [review-repairs-model-comparison-20261027.json](review-repairs-model-comparison-20261027.json) | [review-repairs-model-comparison-20261027.md](review-repairs-model-comparison-20261027.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [runtime-fixes-20261021.json](runtime-fixes-20261021.json) | [runtime-fixes-20261021.md](runtime-fixes-20261021.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [search-audit-5000-20261019.json](search-audit-5000-20261019.json) | [search-engine-audit-20261019.md](search-engine-audit-20261019.md) | 当时引擎/内容/代理/后端/运行审计分项结果 |
| [search-audit-5000-content-20261019.json](search-audit-5000-content-20261019.json) | [search-engine-audit-20261019.md](search-engine-audit-20261019.md) | 当时引擎/内容/代理/后端/运行审计分项结果 |
| [search-audit-5000-content-proxy9876-20261019.json](search-audit-5000-content-proxy9876-20261019.json) | [search-engine-audit-20261019.md](search-engine-audit-20261019.md) | 当时引擎/内容/代理/后端/运行审计分项结果 |
| [search-audit-5000-proxy9876-20261019.json](search-audit-5000-proxy9876-20261019.json) | [search-engine-audit-20261019.md](search-engine-audit-20261019.md) | 当时引擎/内容/代理/后端/运行审计分项结果 |
| [search-audit-5000-recheck-20261019.json](search-audit-5000-recheck-20261019.json) | [search-engine-audit-20261019.md](search-engine-audit-20261019.md) | 当时引擎/内容/代理/后端/运行审计分项结果 |
| [search-audit-5001-20261019.json](search-audit-5001-20261019.json) | [search-engine-audit-20261019.md](search-engine-audit-20261019.md) | 当时引擎/内容/代理/后端/运行审计分项结果 |
| [search-audit-5001-backends-20261019.json](search-audit-5001-backends-20261019.json) | [search-engine-audit-20261019.md](search-engine-audit-20261019.md) | 当时引擎/内容/代理/后端/运行审计分项结果 |
| [search-audit-5002-20261019.json](search-audit-5002-20261019.json) | [search-engine-audit-20261019.md](search-engine-audit-20261019.md) | 当时引擎/内容/代理/后端/运行审计分项结果 |
| [search-audit-5002-content-20261019.json](search-audit-5002-content-20261019.json) | [search-engine-audit-20261019.md](search-engine-audit-20261019.md) | 当时引擎/内容/代理/后端/运行审计分项结果 |
| [search-audit-5002-direct-20261019.json](search-audit-5002-direct-20261019.json) | [search-engine-audit-20261019.md](search-engine-audit-20261019.md) | 当时引擎/内容/代理/后端/运行审计分项结果 |
| [search-audit-5002-expanded-20261019.json](search-audit-5002-expanded-20261019.json) | [search-engine-audit-20261019.md](search-engine-audit-20261019.md) | 当时引擎/内容/代理/后端/运行审计分项结果 |
| [search-audit-5002-pipeline-20261019.json](search-audit-5002-pipeline-20261019.json) | [search-engine-audit-20261019.md](search-engine-audit-20261019.md) | 当时引擎/内容/代理/后端/运行审计分项结果 |
| [search-audit-biomedical-services-20261019.json](search-audit-biomedical-services-20261019.json) | [search-engine-audit-20261019.md](search-engine-audit-20261019.md) | 当时引擎/内容/代理/后端/运行审计分项结果 |
| [search-audit-github-anonymous-20261019.json](search-audit-github-anonymous-20261019.json) | [search-engine-audit-20261019.md](search-engine-audit-20261019.md) | 当时引擎/内容/代理/后端/运行审计分项结果 |
| [search-audit-github-anonymous9876-20261019.json](search-audit-github-anonymous9876-20261019.json) | [search-engine-audit-20261019.md](search-engine-audit-20261019.md) | 当时引擎/内容/代理/后端/运行审计分项结果 |
| [search-audit-local-rag-20261019.json](search-audit-local-rag-20261019.json) | [search-engine-audit-20261019.md](search-engine-audit-20261019.md) | 当时引擎/内容/代理/后端/运行审计分项结果 |
| [search-audit-pubmed-knownpaper-20261019.json](search-audit-pubmed-knownpaper-20261019.json) | [search-engine-audit-20261019.md](search-engine-audit-20261019.md) | 当时引擎/内容/代理/后端/运行审计分项结果 |
| [search-audit-runtime-20261019.json](search-audit-runtime-20261019.json) | [search-engine-audit-20261019.md](search-engine-audit-20261019.md) | 当时引擎/内容/代理/后端/运行审计分项结果 |
| [search-audit-searxng-backends-20261019.json](search-audit-searxng-backends-20261019.json) | [search-engine-audit-20261019.md](search-engine-audit-20261019.md) | 当时引擎/内容/代理/后端/运行审计分项结果 |
| [search-audit-summary-20261019.json](search-audit-summary-20261019.json) | [search-engine-audit-20261019.md](search-engine-audit-20261019.md) | 当时引擎/内容/代理/后端/运行审计分项结果 |
| [search-connectivity-20261028.json](search-connectivity-20261028.json) | [search-connectivity-20261028.md](search-connectivity-20261028.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [search-recovery-20261020.json](search-recovery-20261020.json) | [search-recovery-20261020.md](search-recovery-20261020.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [search-stability-final-20261016.json](search-stability-final-20261016.json) | [search-stability-20261016.md](search-stability-20261016.md) | 当时检索/relay/运行稳定性检查 |
| [search-stability-relay-final-20261016.json](search-stability-relay-final-20261016.json) | [search-stability-20261016.md](search-stability-20261016.md) | 当时检索/relay/运行稳定性检查 |
| [search-stability-runtime-20261016.json](search-stability-runtime-20261016.json) | [search-stability-20261016.md](search-stability-20261016.md) | 当时检索/relay/运行稳定性检查 |
| [semantic-pilot-20261014-final.json](semantic-pilot-20261014-final.json) | [semantic-pilot-20261014.md](semantic-pilot-20261014.md) | 旧语义试跑/正例/真实摘录/阶段结果；非独立全面验收 |
| [semantic-pilot-20261014-optimized-v2.json](semantic-pilot-20261014-optimized-v2.json) | [semantic-pilot-20261014.md](semantic-pilot-20261014.md) | 旧语义试跑/正例/真实摘录/阶段结果；非独立全面验收 |
| [semantic-pilot-20261014-optimized.json](semantic-pilot-20261014-optimized.json) | [semantic-pilot-20261014.md](semantic-pilot-20261014.md) | 旧语义试跑/正例/真实摘录/阶段结果；非独立全面验收 |
| [semantic-pilot-20261014.json](semantic-pilot-20261014.json) | [semantic-pilot-20261014.md](semantic-pilot-20261014.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [semantic-real-excerpts-20261014-final.json](semantic-real-excerpts-20261014-final.json) | [semantic-pilot-20261014.md](semantic-pilot-20261014.md) | 旧语义试跑/正例/真实摘录/阶段结果；非独立全面验收 |
| [semantic-real-excerpts-20261014.json](semantic-real-excerpts-20261014.json) | [semantic-pilot-20261014.md](semantic-pilot-20261014.md) | 旧语义试跑/正例/真实摘录/阶段结果；非独立全面验收 |
| [semantic-scope-positives-20261014.json](semantic-scope-positives-20261014.json) | [semantic-pilot-20261014.md](semantic-pilot-20261014.md) | 旧语义试跑/正例/真实摘录/阶段结果；非独立全面验收 |
| [semantic-stage-final-20261014.json](semantic-stage-final-20261014.json) | [semantic-pilot-20261014.md](semantic-pilot-20261014.md) | 旧语义试跑/正例/真实摘录/阶段结果；非独立全面验收 |
| [sidebar-5002-20261030.json](sidebar-5002-20261030.json) | [sidebar-5002-20261030.md](sidebar-5002-20261030.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [spatial-research-collection-patched-20261020.json](spatial-research-collection-patched-20261020.json) | [spatial-research-collection-patched-20261020.md](spatial-research-collection-patched-20261020.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [spatial-research-search-patched-20261020.json](spatial-research-search-patched-20261020.json) | [spatial-research-search-patched-20261020.md](spatial-research-search-patched-20261020.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [synthesis-trace-20261026.json](synthesis-trace-20261026.json) | [synthesis-trace-20261026.md](synthesis-trace-20261026.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [test001-review-20261027.json](test001-review-20261027.json) | [test001-review-20261027.md](test001-review-20261027.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [themes-5002-20261030.json](themes-5002-20261030.json) | [current-status.md](current-status.md) | 三主题部署/环境与卷保持结果；没有独立同名MD |
| [trace-review-7162eae1-20261026.json](trace-review-7162eae1-20261026.json) | [trace-review-7162eae1-20261026.md](trace-review-7162eae1-20261026.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [ui-chinese-20261030.json](ui-chinese-20261030.json) | [ui-chinese-20261030.md](ui-chinese-20261030.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [ui-workspace-20261028.json](ui-workspace-20261028.json) | [ui-workspace-20261028.md](ui-workspace-20261028.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [web-run-log-review-20261021-7759b63e.json](web-run-log-review-20261021-7759b63e.json) | [web-run-log-review-20261021-7759b63e.md](web-run-log-review-20261021-7759b63e.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |
| [web-run-log-review-20261021.json](web-run-log-review-20261021.json) | [web-run-log-review-20261021.md](web-run-log-review-20261021.md) | 同名说明的结构化结果；按记录日期和验证范围解读 |

## 截图与说明对应

| 图片 | 对应记录 | 证明范围 |
| --- | --- | --- |
| [sidebar-5002-20261030/collapsed.png](sidebar-5002-20261030/collapsed.png) | [sidebar-5002-20261030.md](sidebar-5002-20261030.md) | 当时页面预览，不证明真实研究质量 |
| [sidebar-5002-20261030/expanded.png](sidebar-5002-20261030/expanded.png) | [sidebar-5002-20261030.md](sidebar-5002-20261030.md) | 当时页面预览，不证明真实研究质量 |
| [ui-chinese-20261030/home.png](ui-chinese-20261030/home.png) | [ui-chinese-20261030.md](ui-chinese-20261030.md) | 当时页面预览，不证明真实研究质量 |
| [ui-chinese-20261030/settings.png](ui-chinese-20261030/settings.png) | [ui-chinese-20261030.md](ui-chinese-20261030.md) | 当时页面预览，不证明真实研究质量 |
| [ui-workspace-20261028/ui-home-dark.png](ui-workspace-20261028/ui-home-dark.png) | [ui-workspace-20261028.md](ui-workspace-20261028.md) | 当时页面预览，不证明真实研究质量 |
| [ui-workspace-20261028/ui-home-desktop.png](ui-workspace-20261028/ui-home-desktop.png) | [ui-workspace-20261028.md](ui-workspace-20261028.md) | 当时页面预览，不证明真实研究质量 |
| [ui-workspace-20261028/ui-home-mobile.png](ui-workspace-20261028/ui-home-mobile.png) | [ui-workspace-20261028.md](ui-workspace-20261028.md) | 当时页面预览，不证明真实研究质量 |
| [ui-workspace-20261028/ui-login-desktop.png](ui-workspace-20261028/ui-login-desktop.png) | [ui-workspace-20261028.md](ui-workspace-20261028.md) | 当时页面预览，不证明真实研究质量 |
| [ui-workspace-20261028/ui-report-desktop.png](ui-workspace-20261028/ui-report-desktop.png) | [ui-workspace-20261028.md](ui-workspace-20261028.md) | 当时页面预览，不证明真实研究质量 |

## 仓库相邻文档与构建清单

| 路径 | 对应什么 | 定位 |
| --- | --- | --- |
| [README](../README.md) | 项目介绍、通用使用和文档导航 | 用户入口，当前开发状态到docs查 |
| [AGENTS.md](../AGENTS.md) | 工程接续约束和开发入口 | 工作规则，优先服从用户最新要求；本轮未修改 |
| [research_verify说明](../local_deep_research/research_verify/README.md) | 当前模块、可选QC及旧CLI/兼容边界 | 当前模块说明；区别写后修订与保存前审计 |
| [UI说明](../local_deep_research/overlay/ui/README.md) | 中文显示、内容保护及UI安装维护 | 模块维护说明 |
| [LLM-MODELS](../local_deep_research/LLM-MODELS.md) | 9月模型端点/切换记录 | 历史；S1默认与旧命令不代表当前 |
| [ENGINE_STATUS](../ldr-monitor/ENGINE_STATUS.md) | 9月引擎探针结果 | 历史；非当前健康状态 |
| [ENGINE_ARCHITECTURE](../ldr-monitor/ENGINE_ARCHITECTURE.md) | 9月搜索架构与主工具切换 | 历史；非当前来源池说明 |
| [完整overlay清单](../deployment/overlay-manifest.json) | 53应用覆盖目标 | 构建输入，不是测试结果 |
| [UI清单](../deployment/ui-overlay-manifest.json) | 29UI目标 | 构建输入，不是单独完整后端 |
| [检索清单](../deployment/search-overlay-manifest.json) | 定向检索补丁 | 阶段构建范围 |
| [来源修复清单](../deployment/generic-source-overlay-manifest.json) | 定向来源补丁 | 阶段构建范围 |
| [证据流程清单](../deployment/evidence-flow-overlay-manifest.json) | 定向核对流程补丁 | 阶段构建范围 |
| [trace清单](../deployment/synthesis-trace-overlay-manifest.json) | 定向过程记录补丁 | 阶段构建范围 |
| [检索恢复profile](../deployment/search-restoration-profile.json) | 恢复对照使用的配置快照 | 不是本机实时环境 |
| `local-deep-research/**/README*`与`docs/` | 上游项目源码文档 | 上游快照，不纳入本次项目记录逐份重编 |

## 仓库外与私有资料

| 位置 | 内容 | 本轮处理 |
| --- | --- | --- |
| `/data/ningh/nh/LDR-资料索引.md` | 本机跨工作区导航 | 已更新指向本集合 |
| `/data/ningh/nh/astro-dra/docs/` | main本地生产记录与旧文档副本 | 添加导航；独有5000记录补入本集合，未复制5002应用功能 |
| `/data/ningh/nh/astro-dra/reports/` | 原始生成报告和模型对照索引 | Git忽略的本地产物；开发worktree没有reports目录，不复制 |
| `/data/ningh/nh/ldr-experiments/` | 实验输入输出、失败日志、临时构建、Cookie/账号等私有资料 | 只登记用途，按原记录定位，不读出凭据或复制 |
| `/data/ningh/nh/ldr-test-5002-backups/` | 5002阶段配置/模块/数据库等备份 | 只定位；每次备份范围不同，不等于都有全卷 |
| `/data/ningh/nh/ldr-5000-backups/` | 5000切换前数据与配置备份 | 以5000部署记录为准 |
| `/data/ningh/nh/archive/ldr-history-20261016/` | 早期方案、迁移保留资料、清理记录及旧配置 | 旧配置可能含凭据；已删除的旧数据不能靠文档恢复 |
| 同级旧`local_deep_research/`、`local-deep-research/`、`ldr_ori/`、`ldr-official-lab/` | 旧部署、原版或对照实验 | 本轮登记边界，不视作当前5002开发入口 |
