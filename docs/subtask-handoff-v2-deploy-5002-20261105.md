# 子任务第二版部署5002

日期：2026-11-05。按用户明确要求完成部署并重启应用；未合入main或更新5000。[部署结果](subtask-handoff-v2-deploy-5002-20261105.json) · [昨日实现及测试](subtask-handoff-v2-20261104.md)。

## 版本与部署

直接使用昨日最终测试镜像90cc95ab9a4354786514766d6a44d4d2768f44ec1567d60b77075f2c2b654bef，添加部署标签`astro-dra:subtask-handoff-v2-5002-20261105`，没有重新构建另一版。相关5个源码/测试文件SHA与442回归记录一致。941包文件相对第一版只改变Agent、subtask_handoff和新增subtask_research；实际运行安装三目标SHA与测试构建相符，核查evidence_flow、共享generation、原synthesis_trace哈希不变。

当前容器可见3项研究均有结束状态，最近62827275已完成。备份原env、Compose及运行元数据后，仅更新主工作区`.env.test-5002`的ASTRO_DRA_IMAGE；候选Compose逐项比较仅image变化。沿原项目/原Compose执行`up -d --no-build --no-deps local-deep-research`，保留原卷。

新容器`bc70fe3d28e703b2a4c46d91f20267795ac1b1fbb69d1c8eba6502b64f8e76ef`于`2026-11-05T00:38:14.872675906Z`启动，即北京时间08:38:14。healthy，入口跟随至登录页200、登录页200，启动ERROR/Traceback行0。

## 验证与不变项

- 部署前断网一次性容器以UID1000运行真实LangGraph/工具线程和固定模型：两个并发任务共4次搜索＋2次交付，来源隔离、trace目录0700/文件0600通过，0次API调用。
- 实际运行容器以UID1000导入新模块成功；Agent源码已接入新控制器。这是安装/入口确认，本次未启动新真实研究，不宣称已执行生产收尾流程。
- 运行环境逐键值、挂载和端口相同；模型、核查、三源、500预算及自动全文配置未调整。5000、5002 SearXNG和relay的ID及启动时间不变。账号/中文/主题等继承原镜像内容。
- 首次脚本直接比较Docker Env列表，因顺序不同触发断言；随后核对全部键值一致，没有为消除断言修改运行参数。文档补丁首次因整行匹配失败未落盘，修正后完成，不影响部署。

## 备份与回退

私有目录`/data/ningh/nh/ldr-experiments/subtask-handoff-v2-deploy-5002-20261105/`，目录0700、文件0600。含`.env.pre-deploy`、`compose.pre-deploy.yaml`、前后inspect/Compose、安装测试、启动日志和结果；私有配置不提交。

回退时恢复该`.env.pre-deploy`到`/data/ningh/nh/astro-dra/.env.test-5002`，再沿原项目/Compose仅重建应用。旧第一版标签`astro-dra:subtask-handoff-5002-20261104`及84c1b5fd…镜像仍保留。本次没有数据库结构变化，不恢复或删除卷。

## 边界与下一步

本轮确认安装、重启和服务可用，没有重跑完整研究或网页账号保存/导出，也没有读取解密用户库、改写历史报告或新增模型调用。沿用昨日442回归及有限实跑的范围，不当作总体语义准确性验收。新任务使用第二版，旧任务不重写。

下一步观察用户新任务的预算、材料、交付和最终表述；核查按原约定另行优化。未提交推送合入main，Git fetch仍因HTTPS认证失败。
