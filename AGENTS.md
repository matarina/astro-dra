# LDR 工程接续

开始任何开发任务，先阅读 docs/development-progress.md，再阅读其引用的基线和工程计划；重查 Git 状态与远程变化。
用户当前优先级为结论可溯源（M3-A），随后真实性与条件（M1）、全文关键词（M2）、综合验收（M3-B/M4）。
部署补丁位于 local_deep_research/，根目录 deployment/overlay-manifest.json 管理安装目标。旁置 local-deep-research/ 的改动不会自动部署。
不要把文档计划、合成样本或结构契约视为生产功能已实现。待核验/关闭核验不能等价为通过。
会话结束更新 docs/development-progress.md 的改动、验证、限制和下一步。遵守用户最新指令。
