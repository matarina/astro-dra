# Astro DRA

当前 Local Deep Research 的源码及部署补丁快照。

- `local-deep-research/`：上游源码（基于提交 `2915dc05a`），包含当前本地修改。
- `local_deep_research/`：5000 端口服务的部署配置、自定义补丁、验证模块及测试。
- `ldr-monitor/`：搜索引擎监控脚本与历史说明。

API 密钥已替换为环境变量；原有含密钥的 Git 历史不包含在此仓库中。

## 部署

在 `local_deep_research/` 下复制 `.env.example` 为 `.env` 并填写凭据，然后执行 `docker compose up -d --build`。部署配置包含原机器的日志路径和代理地址，迁移时需按环境调整。Dockerfile 使用上游 `latest` 镜像并覆盖补丁，不从旁边的上游源码目录构建。

## 测试

安装 pytest、pytest-asyncio、respx、pydantic-settings、httpx、loguru 后，从仓库根目录执行：

```bash
PYTHONPATH=local_deep_research python -m pytest local_deep_research/tests
```

上游项目为 LearningCircuit/local-deep-research，许可证见 `local-deep-research/LICENSE`。
