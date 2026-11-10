# 文档整理与核查记录（2026-11-04）

用户要求完整整理开发和记录文档。本轮仅处理Markdown及本次整理清单JSON，没有执行应用开发、模型调用、研究任务、账号创建、构建、部署或重启。

## 整理结果

当前状态、待办、短接续、研究流程、源码边界、部署和5002说明已分开维护；[总索引](README.md)按问题和功能导航，[完整目录](document-catalog.md)逐项列出全部67份Markdown、106份JSON及9张截图。这里的JSON数量包含本轮核查清单，不表示106轮成功测试。

49份日期记录增加了“文档定位”提示，区分当时实现、部署、诊断、撤回试验和旧严格阶段；原记录正文保持。原始JSON与截图不改写。相邻模型/监控旧说明增加历史提示，research_verify说明更新了写后核对与保存前QC的区别。AGENTS.md未修改。

## 两工作区如何对应

- 开发文档在`astro-dra-ui-5002/docs/`集中维护，当前内容不会自动代表main已包含5002功能。
- main独有的5000部署MD/JSON补入开发集合；main原文保留，并增加`docs/README.md`和旧入口导航提示。
- 两份开发流水各有独有事件，均保留原始快照；没有用一份覆盖另一份历史。main的README使用者说明保持原样，开发工作区README只加文档入口。
- 本机`LDR-资料索引.md`更新为跨工作区入口。私有实验、报告、账号/凭据、环境文件及数据备份均不复制进文档集合。

## 原文快照

下列文件保持整理前原始字节，放在原docs目录以维持原相对路径的基准。文件名中的20261104是归档日期，正文事件仍按原日期理解。原始哈希记录在[机器核查结果](documentation-audit-20261104.json)。

| 原文件/来源 | 原始快照 |
| --- | --- |
| `astro-dra-ui-5002/docs/development-progress.md` | [development-progress-history-20261104.md](development-progress-history-20261104.md) |
| `astro-dra-ui-5002/docs/current-research-flow-20261016.md` | [research-flow-history-20261104.md](research-flow-history-20261104.md) |
| `astro-dra-ui-5002/docs/deployment.md` | [deployment-history-20261104.md](deployment-history-20261104.md) |
| `astro-dra-ui-5002/docs/test-instance-5002.md` | [test-instance-5002-history-20261104.md](test-instance-5002-history-20261104.md) |
| `astro-dra-ui-5002/docs/source-layout.md` | [source-layout-history-20261104.md](source-layout-history-20261104.md) |
| `astro-dra/docs/development-progress.md` | [development-progress-main-history-20261104.md](development-progress-main-history-20261104.md) |
| `astro-dra/docs/current-research-flow-20261016.md` | [research-flow-main-history-20261104.md](research-flow-main-history-20261104.md) |

## 私有资料与历史链接

`ldr-experiments/`包含真实输入输出、失败记录、Cookie及账号相关材料；`ldr-test-5002-backups/`与`ldr-5000-backups/`包含不同范围的配置/模块/数据库或卷备份。本轮只核对引用目标是否存在，不解密用户数据库、不读取密钥，也不据文件名承诺可完整恢复。

开发worktree不含Git忽略的reports目录；部分历史文档中的相对`../reports/...`因此无法在本worktree直接打开。实际核对主工作区的`reports/model-comparison-20261027.md`存在，原始报告仍保留在该目录，并不为修链接而复制。旧记录中的`[N](url)`等是语法示例，不作为缺失文件计数。具体引用位置见下方，当前入口不依赖这些相对报告链接。

2026-10-16归档清理中已删除的旧迁移数据和生产大备份不恢复、不重新生成；旧恢复文档不代表有对应备份。上游快照全部文档、其他项目和所有私有实验文件不纳入本次逐份重编。

## 验证范围

本轮验证文档集合覆盖、当前入口的本地链接、JSON可解析、原始JSON/截图与快照哈希、变更未涉及应用/配置，以及开始与结束容器ID/镜像一致。没有重新跑应用回归或真实研究，沿用本会话此前403项离线通过和87文件对应的基线，不宣称本次整理提高研究质量。


实际检查结果：目录182项全部覆盖；全部106份JSON解析通过；原两工作区221份JSON/PNG文件哈希保持，补入的生产JSON与main一致；7份原文快照哈希全部一致，49份日期记录去除定位提示后与原文哈希一致；当前10份入口/说明及项目/模块README本地链接无缺失；应用和配置文件变更为0。5000/5002应用及5002搜索/relay容器ID和镜像均未变化。

## 历史记录中的缺失引用

共6处引用，按目标合并为1项；均位于日期记录、旧说明或原文快照，不位于当前10份入口/说明。下表仅登记实际不存在的引用，不伪造结果或补写原始报告。

| 原引用目标 | 涉及记录 | 处理 |
| --- | --- | --- |
| `../reports/model-comparison-20261027.md` | development-progress-history-20261104.md, development-progress-main-history-20261104.md, research-flow-history-20261104.md, research-flow-main-history-20261104.md, review-repairs-model-comparison-20261027.md, test-instance-5002-history-20261104.md | 本地reports未进入开发worktree；原产物按主工作区/原记录查找，不复制私有报告 |
