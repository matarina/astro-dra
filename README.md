# Astro DRA

基于 Local Deep Research 的研究助手源码与 Docker 部署项目，包含检索补丁、引用整理和文献核验模块。支持通过兼容 OpenAI 的接口连接模型，使用 SearXNG 发现检索候选。

| 路径 | 用途 |
| --- | --- |
| `compose.yaml`、`deployment/` | 通用部署入口、固定基础镜像、补丁安装清单和 SearXNG 配置 |
| `local_deep_research/` | 实际安装到镜像的补丁、`research_verify` 模块及其测试；旧部署配置仍保留 |
| `local-deep-research/` | 旁置上游源码快照（导入说明基于提交 `2915dc05a`），包含本地修改 |
| `ldr-monitor/` | 原部署的诊断脚本与历史说明，使用前需检查机器路径 |
| `docs/` | 当前流程、部署说明、测试记录及历史工程计划 |

API 密钥通过环境变量传入。`.env`、本地部署覆盖文件、日志和数据不应提交 Git。

当前默认研究来源为 **PubMed、SearXNG、Europe PMC**。来源保留完整摘要及可取得的原文，最终成文后结合章节和表格核对引用；有原文支持且独立确认的错误可局部修订。核对失败或证据不足仍可输出报告，不使用强制准入或删句门槛。保存前逐引用语义审计默认关闭，PubMed自动全文默认关闭，按需取文保留。

**这不保证引文语义准确、论文全集覆盖或逐篇JIF条件已核实。** 当前实现与已知限制见[5002累计变化](docs/5002-vs-main-20261028.md)和[修复及模型对照](docs/review-repairs-model-comparison-20261027.md)。旧严格核验计划仅作历史参考。

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

访问 <http://localhost:5000> 并注册初始账号。默认仅监听宿主机回环地址；远程访问和已有部署迁移见 [部署说明](docs/deployment.md)。研究表单可按次选择模型/提供方；环境配置的默认值保持不变。账号创建后可将 `LDR_APP_ALLOW_REGISTRATIONS=false`，执行 `docker compose up -d` 应用配置。

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

## 当前流程与历史计划

当前行为以[累计变化](docs/5002-vs-main-20261028.md)、[最近实现与限制](docs/review-repairs-model-comparison-20261027.md)及[开发进度](docs/development-progress.md)为准。模型收到的来源材料、写作及核对过程可私有保存到`/data/research_traces`，不追加到报告正文；生成报告目录`reports/`、私有`.env`、数据库和日志不提交Git。

[早期严格核验工程计划](docs/ldr-verification-engineering-plan.md)保留历史设计，不能作为当前功能或逐篇JIF验收已实现的证明。

## 开发接续

每次开发先读 [开发进度记录](docs/development-progress.md) 与 [M0 工程基线](docs/verification-foundation-20261012.md)。当前以有用研究报告、证据连续性和通用引用归属修复为主，不恢复旧的强制准入流程。
