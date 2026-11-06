# 整理与部署基线验证（2026-10-12）

> 文档定位：历史工程基线；不是当前测试数量。本页记录当时过程；当前状态见[状态总览](current-status.md)，有效后续见[待办](roadmap.md)。

代码基线为 `d7d874b`，新增通用部署入口在 `work/ldr-20261012` 整理。

## 已完成验证

- 使用现有 `verify-venv`（Python 3.14）执行 `PYTHONPATH=local_deep_research python -m pytest local_deep_research/tests -q`：55 passed。
- `docker compose --env-file .env.example config --quiet`：通过。示例配置仅用于插值验证。
- `docker build -t astro-dra:verify-20261012 -f deployment/Dockerfile .`：通过，五个补丁目标存在，语法与核验模块导入检查通过。
- 新镜像使用临时数据单独启动，继承入口切换到 `ldruser`；应用版本为 1.10.7，`/api/v1/health` 返回 HTTP 200、`status=ok`。
- 固定 digest 的 SearXNG 使用仓库配置单独启动，`/healthz` 返回 `OK`。
- 验证容器未发布宿主端口，完成后停止并自动移除，未切换生产服务。

LDR 基础镜像：`localdeepresearch/local-deep-research@sha256:ce95481a35d3eebc2c1ae7bd34fad426108c3fb8d1a22f66c9e772276869c2f0`。

SearXNG 镜像：`searxng/searxng@sha256:6dd0dffc05a75d92bbacd858953b4e93b8f709403c3fb1fb8a33ca8fd02e40a4`。

## 尚未验收

本次未执行真实模型研究、外部检索质量验证、数据迁移、完整报告及导出验收，也未实现严格文献验证计划中的新能力。55 项模块测试与启动检查不能替代这些验收。基础镜像和 ddgs 版本固定，pip 传递依赖及测试依赖尚未完全锁定。
