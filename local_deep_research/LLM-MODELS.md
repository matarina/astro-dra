# LDR 可用 LLM 模型端点

> 历史说明：本页为2026年9月的模型/搜索基线，默认模型、来源、代理及操作路径不代表当前实例。最新见[当前状态](../docs/current-status.md)及[文档目录](../docs/document-catalog.md)。

> 更新日期：2026-09-18
> 当前默认：**S1-DeepResearch-32B**（生成 + 判卷）— 已实测容器内调用成功

本文件记录 LDR 主实例（5000 端口）可用的 OpenAI 兼容模型端点，便于日后切换。

## 当前生效配置（docker-compose.yml）

| 项 | 值 |
|----|----|
| Provider | `openai_endpoint` |
| 生成模型 URL | `http://27.30.76.162:6183/ai/v1` |
| 生成模型 | `S1-DeepResearch-32B` |
| API Key | `EMPTY`（免鉴权） |
| 判卷模型 URL | `http://27.30.76.162:6183/ai/v1` |
| 判卷模型 | `S1-DeepResearch-32B` |
| 判卷 API Key | `EMPTY`（免鉴权） |

## 可用模型清单

### 1. deepseek-v4-flash（pi 端点 local-vllm）— 曾任默认
- 端点：`http://27.30.76.162:6183/v1`
- API Key：`${LDR_BENCHMARK_EVALUATION_ENDPOINT_API_KEY}`
- 上下文：1,000,000；max_tokens：8192
- 快速回退：`cp docker-compose.yml.bak_deepseek_20260918_053622 docker-compose.yml && docker compose up -d --force-recreate --no-deps local-deep-research`

### 2. deepseek-v4.1-flash（pi 端点 local-vllm-v41）
- 端点：`http://10.0.11.40:8000/v1`
- API Key：`EMPTY`（免鉴权，填任意非空即可）
- 模型：`deepseek-v4.1-flash`
- 上下文：1,000,000

### 3. S1-DeepResearch-32B ⭐（vLLM 本地服务）— 当前默认
- 端点：`http://27.30.76.162:6183/ai/v1`
- API Key：无需（填 `EMPTY`）
- 模型：`S1-DeepResearch-32B`
- 上下文：max_model_len=**16384**（16K，较短；deepseek 是 1M）
- ⚠️ 深度思考模型：输出带 `thinking` 推理链前缀；要求模型输出极短/严格 JSON 的内部任务可能受影响（LDR 多数做容错解析，以实际行为为准）

> 说明：pi agent 的配置（`~/.pi/agent/models.json`）中模型 1、2 即上述两套，模型 3 为用户额外添加。

---

## 切换方法

LDR 模型通过 compose 环境变量注入（运行时最高优先级）。要切换模型：

1. 编辑 `~/nh/local_deep_research/docker-compose.yml`，
   把以下 6 处改成目标模型的 URL / key / model：
   - `LDR_LLM_OPENAI_ENDPOINT_URL`
   - `LDR_LLM_OPENAI_ENDPOINT_API_KEY`
   - `LDR_LLM_MODEL`
   - `LDR_BENCHMARK_EVALUATION_ENDPOINT_URL`
   - `LDR_BENCHMARK_EVALUATION_ENDPOINT_API_KEY`
   - `LDR_BENCHMARK_EVALUATION_MODEL`
2. 用**强制重建**使环境变量生效（`restart` 不会重新读环境变量）：
   ```bash
   cd ~/nh/local_deep_research
   export COMPOSE_PROJECT_NAME=local_deep_research
   docker compose up -d --force-recreate --no-deps local-deep-research
   ```

### 示例：切换到 S1-DeepResearch-32B
```yaml
LDR_LLM_OPENAI_ENDPOINT_URL=http://27.30.76.162:6183/ai/v1
LDR_LLM_OPENAI_ENDPOINT_API_KEY=EMPTY
LDR_LLM_MODEL=S1-DeepResearch-32B
LDR_BENCHMARK_EVALUATION_ENDPOINT_URL=http://27.30.76.162:6183/ai/v1
LDR_BENCHMARK_EVALUATION_ENDPOINT_API_KEY=EMPTY
LDR_BENCHMARK_EVALUATION_MODEL=S1-DeepResearch-32B
```
> 注意：S1 的上下文只有 16K。LDR 一般会按 vLLM `/models` 报告的 `max_model_len` 自动限制发送长度，无需手工设参；若实测出现 `context length exceeded`/超长报错，再来处理上下文截断。

### 示例：切换到 deepseek-v4.1-flash
```yaml
LDR_LLM_OPENAI_ENDPOINT_URL=http://10.0.11.40:8000/v1
LDR_LLM_OPENAI_ENDPOINT_API_KEY=EMPTY
LDR_LLM_MODEL=deepseek-v4.1-flash
LDR_BENCHMARK_EVALUATION_ENDPOINT_URL=http://10.0.11.40:8000/v1
LDR_BENCHMARK_EVALUATION_ENDPOINT_API_KEY=EMPTY
LDR_BENCHMARK_EVALUATION_MODEL=deepseek-v4.1-flash
```
