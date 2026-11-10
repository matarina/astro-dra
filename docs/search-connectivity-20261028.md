# 5002三源检索断连（2026-10-28）

> 文档定位：主要断连已修；零命中/失败提示待做。本页记录当时过程；当前状态见[状态总览](current-status.md)，有效后续见[待办](roadmap.md)。

用户报告连续任务只生成“所有工具均无结果”的未完成说明。对照13:59:57（05:59:57 UTC）任务 `e9f17c77-2685-4e3e-ba23-7fefa2136122` 的私有中间记录，10个tool_results记录，collector_sources确为0条；报告描述与实际空来源一致。

## 根因与证据

三源共享的代理转发链路出现按UID区分的连通性故障。PubMed/Europe PMC请求约0.01秒即ConnectionError/RemoteDisconnected，SearXNG返回Bing HTTP protocol error；relay日志为upstream_connect_failed / ConnectionRefusedError，健康检查失败。检索连接失败被现有引擎包装成空结果，Agent不断换词仍无材料，最终生成未完成说明。错误发生在获取候选之前，不能归因于相关性模型、摘要扩写或报告引用编号。

宿主127.0.0.1:9876上的sing-box进程仍运行。宿主与host网络relay的netns一致。对同一端口固定GID/UID对照：UID1006/GID1000连接成功（connect_ex=0），UID1000/GID1007拒绝（111）；root和1001也拒绝。由此确认UID差异，不能简单说宿主代理进程已停止。具体主机防火墙/策略规则及改变时间未确认；无sudo只读iptables权限，未修改或绕过主机规则。

上次UI部署只变8模板和2资源，后端927文件已比对、环境和来源配置未改。此次实测无需改UI或研究代码即恢复网络，说明根因位于独立代理链路；不能据此声称知道宿主策略何时变化。

## 修复

Compose增加 `PROXY_RELAY_UID` / `PROXY_RELAY_GID`，默认仍1000；为当前5002私有env设置1006:1007，与被允许使用宿主代理的ningh用户一致。增加可单独锁定的 `PROXY_RELAY_IMAGE`，当前保留原 `astro-dra:search-stability-20261016-v2`，避免随着应用UI镜像变化重建成别的relay镜像。示例env注明按宿主代理所属账号 `id -u` / `id -g` 设置。

只重建5002的proxy-relay，保留host网络、只读文件系统、cap_drop/no-new-privileges、端口和转发程序；未放宽安全规则、未加特权、未修改宿主代理配置。5002应用、5000应用与SearXNG的容器ID及启动时间保持不变。运行用主工作区Compose/env和UI开发分支对应源码已同步；未提交/推送/合并。

## 验证和限制

- 原始复现命令在5002容器内对三个服务发相同主题查询：修复前三源均失败；修复后同题PubMed/Europe PMC有匹配，SearXNG返回10条。总匹配数不等于下载到的论文数。
- 新增通用 `scripts/check_search_connectivity.py`，以cancer为默认连通性探针，从实际应用容器请求三源并检查返回条目；PubMed/Europe PMC各3条，SearXNG各轮7—10条，HTTP200，无Bing错误。无模型调用或新研究写入；异常只记类型，不输出可能含凭据的异常字符串。
- 原生PubMed和Europe PMC的 `_get_previews` 各取得2条，含摘要字段；模型相关性及完整生成未重跑。
- Bing仍有独立的偶发空结果：相同主题请求部分返回10条，部分HTTP200且0条、unresponsive_engines为空；原生SearXNG同题预览也有0条；另外Visium原生预览取得2条。requests与safe_get对照相同，不能把空结果都归因于安全包装或UI。未做题目专用改写/兜底，不把三源连通性恢复夸大为Bing召回稳定或完整报告质量验收。
- relay现为healthy；Compose比较只改relay身份及单独锁定的镜像配置，应用环境、模型和数据卷未改。配置验证、脚本AST和diff检查通过；未修改研究Python代码，未重复全量单测。

从任意有本仓库脚本的目录执行：

```bash
docker exec -i astro-dra-test-5002-local-deep-research-1 \
  /install/.venv/bin/python - < scripts/check_search_connectivity.py
```

新任务才会重新检索；已保存的未完成报告不会自动补写。后续如继续完善，应区分工具连接失败与正常零命中，并在研究启动前提供依赖健康提示；这两项本轮尚未实现。

完整私有日志、修复前容器/Compose/env和探针在 `/data/ningh/nh/ldr-experiments/search-outage-20261028`（0700，含私有env，不提交）。恢复配置时注意旧UID1000仍可能断连，不能直接把恢复配置等同于恢复检索。公开证据见同名JSON。
