# Astro DRA

Astro DRA 是基于 [Local Deep Research](https://github.com/LearningCircuit/local-deep-research) 的 AI 研究助手。输入研究问题后，系统会检索网页和学术文献、整理来源材料，并生成带参考文献的研究报告。项目提供 Web 界面，使用 Docker Compose 部署，适合文献调研、资料整理和专题研究。

## 主要功能

- **多来源检索**：整合 PubMed、SearXNG 和 Europe PMC，检索网页、论文元数据和摘要。
- **研究报告生成**：支持普通研究与详细报告，可在网页中查看历史记录、引用和导出结果。
- **证据与引用整理**：保留来源材料，按需获取原文，整理论文身份、版本关系和引用编号。
- **事实一致性检查**：结合来源材料检查最终报告，并对有证据支持的内容进行局部修订。
- **灵活选择模型**：支持 OpenAI 兼容接口、DeepSeek，以及通过 llama.cpp 接入的模型服务。
- **研究工作台与权限**：中文界面、手机适配、报告目录和专注阅读；普通用户、管理员与独立root审批。
- **子任务材料交付**：研究导航与原文片段分别保留，预算结束后独立收尾，写作前读取原文主体及作用状态。
- **研究过程记录**：可选保存检索、材料选择、写作和核对过程，便于追踪任务。

## 快速启动

以下步骤用于首次部署，在仓库根目录执行。需要安装 Docker Engine、Docker Compose 插件，并准备可用的模型服务。

### 1. 获取项目

```bash
git clone https://github.com/matarina/astro-dra.git
cd astro-dra
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填写模型连接和 SearXNG 密钥：

```dotenv
LDR_LLM_PROVIDER=openai_endpoint
LDR_LLM_OPENAI_ENDPOINT_URL=https://your-provider.example/v1
LDR_LLM_OPENAI_ENDPOINT_API_KEY=your-api-key
LDR_LLM_MODEL=your-model-name
SEARXNG_SECRET=your-random-secret
```

将地址、密钥和模型名替换为服务提供方给出的实际值。可以使用以下命令生成 `SEARXNG_SECRET`：

```bash
openssl rand -hex 32
```

示例配置使用宿主机 `9876` 端口的代理。启动前请按实际网络环境设置代理；使用直连的配置方法见下方[网络与代理](#网络与代理)。

### 3. 构建并启动

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

浏览器访问 <http://localhost:5000>，注册账号后即可开始研究。

## 常用配置

配置文件为根目录 `.env`，可从 `.env.example` 获取完整示例。

| 配置项 | 用途 |
| --- | --- |
| `LDR_LLM_PROVIDER` | 模型提供方，默认 `openai_endpoint` |
| `LDR_LLM_OPENAI_ENDPOINT_URL` | OpenAI 兼容模型服务的 API 地址 |
| `LDR_LLM_OPENAI_ENDPOINT_API_KEY` | 模型服务密钥 |
| `LDR_LLM_MODEL` | 默认模型名称 |
| `LDR_LLM_DEEPSEEK_API_KEY` | 使用原生 DeepSeek 提供方时的密钥 |
| `SEARXNG_SECRET` | SearXNG 使用的随机密钥 |
| `LDR_SEARCH_ENGINE_WEB_PUBMED_API_KEY` | 可选的 PubMed / NCBI API 密钥 |
| `LDR_PORT` | 网页端口，默认 `5000` |
| `LDR_BIND_ADDRESS` | 监听地址，默认 `127.0.0.1` |
| `LDR_APP_ALLOW_REGISTRATIONS` | 是否允许注册，默认 `true` |
| `LDR_LANGGRAPH_AGENT_MAX_UNIQUE_SOURCES` | 常规研究来源容量，默认 `500` |
| `LDR_GENERAL_ENABLE_FACT_CHECKING` | 是否开启报告事实一致性检查，默认 `true` |
| `LDR_RESEARCH_TRACE_ENABLED` | 是否保存研究中间过程，默认 `false` |

修改 `.env` 后，执行以下命令应用配置：

```bash
docker compose up -d --no-deps local-deep-research
```

研究表单的高级选项也可以为单次任务选择模型和提供方。

## 日常管理

```bash
# 查看服务状态
docker compose ps

# 查看应用日志
docker compose logs --tail=100 local-deep-research

# 查看搜索服务日志
docker compose logs --tail=100 searxng

# 停止服务，保留数据
docker compose stop

# 重新启动服务
docker compose up -d
```

### 更新版本

先更新代码，再构建和替换应用容器：

```bash
git pull --ff-only origin main
docker compose up -d --build --no-deps local-deep-research
```

已有部署请沿用原来的 Compose 项目名、环境文件和配置文件；使用过 `-p`、`--env-file` 或多个 `-f` 参数时，更新时也使用同一组参数。更新前完成当前研究任务，并备份数据及私有配置。

## 常见配置与操作

### 修改端口与远程访问

修改 `.env`：

```dotenv
LDR_PORT=5001
LDR_BIND_ADDRESS=0.0.0.0
```

执行 `docker compose up -d` 后，可通过 `http://服务器地址:5001` 访问。需要绑定域名时，可在应用前配置提供 HTTPS 的反向代理。

也可以保留默认回环监听，通过 SSH 转发访问：

```bash
ssh -L 5000:127.0.0.1:5000 user@server
```

随后在本机打开 <http://localhost:5000>。

### 网络与代理

应用和 SearXNG 分别配置代理。

**使用代理**时，在 `.env` 设置应用代理：

```dotenv
LDR_HTTP_PROXY=http://host.docker.internal:9876
LDR_HTTPS_PROXY=http://host.docker.internal:9876
LDR_NO_PROXY=localhost,127.0.0.1,::1,host.docker.internal,searxng
```

同时将 `deployment/searxng/settings.yml` 中 `outgoing.proxies` 的地址改为实际代理地址。内网模型服务需要直连时，将对应主机名或 IP 加入 `LDR_NO_PROXY`。

如果宿主机代理只监听 `127.0.0.1:9876`，可在 `.env` 中加入以下配置，启用项目自带的转发服务：

```dotenv
COMPOSE_PROFILES=loopback-proxy
```

同一宿主机已有转发服务时，直接复用现有服务即可。

**使用直连**时，移除 `deployment/searxng/settings.yml` 中的 `outgoing.proxies` 配置，并创建本地覆盖文件 `compose.direct.local.yml`：

```yaml
services:
  local-deep-research:
    environment:
      HTTP_PROXY: ""
      HTTPS_PROXY: ""
      http_proxy: ""
      https_proxy: ""
```

使用这组配置启动和管理服务：

```bash
docker compose -f compose.yaml -f compose.direct.local.yml up -d --build
```

修改 SearXNG 配置后，重启搜索服务使其生效；直连部署的命令为：

```bash
docker compose -f compose.yaml -f compose.direct.local.yml restart searxng
```

### 数据保存与备份

默认部署使用两个命名卷：

| 数据卷 | 内容 |
| --- | --- |
| `astro-dra_ldr_data` | 账号、研究记录、资料和日志等应用数据 |
| `astro-dra_ldr_config` | 应用配置 |

实际卷名随 Compose 项目名变化。重建应用容器时复用原卷，就能继续使用原账号和研究记录。

备份时保存这两个卷、`.env` 和自定义 Compose 配置。一致性备份可先停止应用，备份完成后再启动。更详细的迁移和回退操作见[部署说明](docs/deployment.md)。

### 注册与过程记录

账号创建完成后，可将 `.env` 中的 `LDR_APP_ALLOW_REGISTRATIONS` 改为 `false`，再应用配置，关闭后续注册。

需要记录研究中间过程时，将 `LDR_RESEARCH_TRACE_ENABLED` 设为 `true`。记录按任务保存到容器内 `/data/research_traces`，随应用数据卷保留；网页报告正文保持正常展示。

## 项目结构

| 路径 | 用途 |
| --- | --- |
| `compose.yaml` | 根目录 Docker Compose 部署入口 |
| `.env.example` | 环境变量示例 |
| `deployment/` | 镜像构建、补丁安装和搜索服务配置 |
| `local_deep_research/` | 安装到运行镜像的应用补丁、研究模块和测试 |
| `local-deep-research/` | 上游源码快照 |
| `scripts/` | 检查、测试和诊断脚本 |
| `docs/` | 部署说明与开发文档 |

## 开发测试

使用 Python 3.12–3.14，在仓库根目录执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
PYTHONPATH=local_deep_research .venv/bin/python -m pytest -q local_deep_research/tests
```

## 致谢与许可

本项目基于 [LearningCircuit/local-deep-research](https://github.com/LearningCircuit/local-deep-research)。上游采用 MIT 许可证，参见 [LICENSE](local-deep-research/LICENSE)。

## 账号与开发接续

普通用户使用简化研究界面，模型与检索参数由服务端统一提供；申请管理员需由独立root审批。首次部署需在服务器初始化root，见[账号说明](docs/account-roles-5002-20261102.md)。2026-11-06本机5000升级按用户要求将既有账号全部设为普通用户，独立root另行创建。

开发前阅读[开发接续](docs/development-progress.md)，当前能力见[当前状态](docs/current-status.md)，未完成事项见[待办](docs/roadmap.md)，完整记录见[文档索引](docs/README.md)。保留有用报告，不恢复旧的强制发布门槛。
