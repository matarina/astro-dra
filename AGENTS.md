# LDR 工程接续

开始任何开发任务，先阅读 docs/development-progress.md，再阅读其引用的基线和工程计划；重查 Git 状态与远程变化。
用户最新方向（2026-10-16）：以生物医学文献检索和有用报告为主，引用核查仅作辅助。删除规则驱动的自动删改、硬性发布门槛与正文核验表；旧M3-A/M1/M2严格准入计划仅作历史参考。当前用户明确的来源池为PubMed、SearXNG与Europe PMC（2026-10-20）；检索恢复与改进以最新接续记录为准。先阅读docs/current-research-flow-20261016.md；后续再调研开源引用支撑核验方法，不能把恢复完整输出等同于幻觉已解决。
2026-10-21最新用户指令：5002关闭保存前逐引用审计，开启LDR原生事实一致性检查；来源预算现为500，完整摘要/分批材料选择、Europe PMC MED路由与正文提取已部署。不要自行重新开启审计、自动删改或题目专用筛选规则。现状见docs/abstract-context-20261021.md、docs/runtime-fixes-20261021.md及接续记录。
部署补丁位于 local_deep_research/，根目录 deployment/overlay-manifest.json 管理安装目标。旁置 local-deep-research/ 的改动不会自动部署。
不要把文档计划、合成样本或结构契约视为生产功能已实现。待核验/关闭核验不能等价为通过。
会话结束更新 docs/development-progress.md 的改动、验证、限制和下一步。遵守用户最新指令。
