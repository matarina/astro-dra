# Astro DRA

基于 Local Deep Research 的研究助手源码与 Docker 部署项目，包含检索补丁、引用整理和文献核验模块。支持通过兼容 OpenAI 的接口连接模型，使用 SearXNG 发现检索候选。

| 路径 | 用途 |
| --- | --- |
| `compose.yaml`、`deployment/` | 通用部署入口、固定基础镜像、补丁安装清单和 SearXNG 配置 |
| `local_deep_research/` | 实际安装到镜像的补丁、`research_verify` 模块及其测试；旧部署配置仍保留 |
| `local-deep-research/` | 旁置上游源码快照（导入说明基于提交 `2915dc05a`），包含本地修改 |
| `ldr-monitor/` | 原部署的诊断脚本与历史说明，使用前需检查机器路径 |
| `docs/` | 源码说明、部署说明及严格文献验证工程计划 |

API 密钥通过环境变量传入。`.env`、本地部署覆盖文件、日志和数据不应提交 Git。

当前核验模块能为 DOI/PMID、年份/IF/语种条件、关键词及结论引用提供检查与标注。**严格文献验证仍处于工程计划阶段**：现有实现不保证最新年度 JIF、正文排除参考文献、逐篇结论证据及所有报告出口严格一致。具体缺口与验收门槛见下方工程计划。

## 部署

需要 Docker Engine 和 Docker Compose 插件。以下命令在仓库根目录执行：

```bash
cp .env.example .env
# 编辑 .env：填写模型端点、模型名、凭据，以及随机 SEARXNG_SECRET
python -c 'import secrets; print(secrets.token_hex(32))'
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
```

访问 <http://localhost:5000> 并注册初始账号。默认仅监听宿主机回环地址；远程访问和已有部署迁移见 [部署说明](docs/deployment.md)。模型相关环境变量会锁定对应的界面设置。账号创建后可将 `LDR_APP_ALLOW_REGISTRATIONS=false`，执行 `docker compose up -d` 应用配置。

根目录部署使用固定 digest 的上游运行镜像，再安装本仓库补丁。**修改 `local-deep-research/` 不会自动进入这个镜像**。补丁映射和源码开发边界见 [源码说明](docs/source-layout.md)。`local_deep_research/docker-compose.yml` 和该目录 Dockerfile 是原机器的历史部署入口，与根目录方案分开使用。

```bash
docker compose logs --tail=100 local-deep-research
docker compose stop
```

数据保存在 `astro-dra_ldr_data` 和 `astro-dra_ldr_config` 命名卷。用户提问另以明文 JSONL 写入 `/data/logs/user_questions.log`；`LDR_ENABLE_FILE_LOGGING` 不控制这份独立提问日志。

## 测试

Python 3.12–3.14。从仓库根目录运行核验模块的独立测试：

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
PYTHONPATH=local_deep_research .venv/bin/python -m pytest -q local_deep_research/tests
```

这些测试验证模块逻辑，不能代替联网核验、完整研究流程或严格核验验收。上游完整测试使用其独立依赖环境，说明见 [源码说明](docs/source-layout.md)。

上游项目为 [LearningCircuit/local-deep-research](https://github.com/LearningCircuit/local-deep-research)，采用 MIT 许可证，见 [LICENSE](local-deep-research/LICENSE)。

## 严格文献验证工程计划

后续开发与验收参见 [工程计划](docs/ldr-verification-engineering-plan.md)。默认使用最新已发布年度的 JIF，关键词仅统计正文并排除参考文献。
