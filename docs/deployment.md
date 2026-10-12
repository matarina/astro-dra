# Docker 部署与迁移

根目录的 `compose.yaml` 使用独立项目名 `astro-dra`，包含应用和 SearXNG。SearXNG 默认配置启用 HTML/JSON 搜索结果，只通过 Compose 内部网络提供服务；应用连接 `http://searxng:8080`，不依赖原机器的 8888 端口或代理。应用继承基础镜像的入口与健康检查，并在入口完成卷权限设置后切换到普通用户。

## 配置

复制根目录 `.env.example` 为 `.env`。填写 `LDR_LLM_OPENAI_ENDPOINT_URL`、`LDR_LLM_MODEL` 和模型凭据，生成随机 `SEARXNG_SECRET`。示例端点和模型名仅为占位，不能直接发起研究。根目录 `.env` 与旧部署目录内的 `.env` 分别管理，旧凭据不会自动迁入。

| 变量 | 默认行为 |
| --- | --- |
| `LDR_PORT` / `LDR_BIND_ADDRESS` | 宿主机 `127.0.0.1:5000` |
| `ASTRO_DRA_IMAGE` | 输出镜像 `astro-dra:local`；发布时用独立版本标签 |
| `LDR_BASE_IMAGE` | 已捕获的上游镜像 digest；更新时需审核补丁兼容性 |
| `LDR_APP_ALLOW_REGISTRATIONS` | 初次启动允许创建账号，之后可关闭 |
| `LDR_VERIFY_ENABLE_VERIFY` | 开启现有标注式核验；关闭不等价于核验通过 |
| `LDR_HTTP_PROXY` / `LDR_HTTPS_PROXY` | 默认不设置应用出站代理 |
| `LDR_NO_PROXY` | 包含 Compose 服务和宿主别名，私有模型端点需另行加入 |
| `LDR_VERIFY_CROSSREF_MAILTO` | 建议替换为维护者联系邮箱 |

其他核验开关在 `VerifyConfig` 中定义，可通过本地 Compose 覆盖文件的 `environment` 添加。Compose 的 `.env` 用于变量插值，并非自动传入所有环境变量。额外搜索引擎密钥也需显式添加环境映射。

若 SearXNG 自身需要代理，修改其 settings 的 `outgoing.proxies` 或通过本地覆盖文件挂载专用 settings；应用代理配置不会自动配置 SearXNG。可以使用 `host.docker.internal` 访问宿主服务，但该服务需要监听容器可访问的地址。

## 验证与远程访问

```bash
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=100 local-deep-research searxng
docker compose exec local-deep-research /install/.venv/bin/python -c 'import research_verify; print(research_verify.__version__)'
```

检查容器健康状态后，用真实模型配置完成一个短研究，核实检索、报告、引用、保存和导出。模块导入和健康检查不能证明模型或所有搜索引擎可用。

远程主机可通过 SSH 转发访问：`ssh -L 5000:127.0.0.1:5000 user@server`。需要直接公开服务时，明确配置监听地址，并由部署环境提供 HTTPS、反向代理与访问控制。

## 已有部署迁移与回滚

旧部署的 `local_deep_research/docker-compose.yml`、本地生产覆盖文件及数据保持原状。新入口不会自动复用它们的数据卷。若宿主机 5000 已被占用，先设置根目录 `.env` 中 `LDR_PORT=5001`，使用独立数据验收。

迁移前记录旧镜像 ID、实际 Compose 文件、卷名、配置和数据库备份。在没有活跃研究任务时进行最终备份与切换。只有确认数据兼容后，才通过本地覆盖文件将新服务的卷映射到实际旧卷；不同版本不要同时写同一数据库。

示例覆盖文件 `compose.migration.local.yml`（将卷名替换为实测名称）：

```yaml
volumes:
  ldr_data:
    external: true
    name: actual_old_data_volume
  ldr_config:
    external: true
    name: actual_old_config_volume
```

部署时显式指定 `docker compose -f compose.yaml -f compose.migration.local.yml up -d`。所有后续管理命令应使用同一组 Compose 文件。

发布前给已验证镜像设置独立标签，并记录镜像 ID。回滚时将 `ASTRO_DRA_IMAGE` 指回保留的旧版本，执行 `docker compose up -d --no-build`。数据库迁移兼容性需单独验证，恢复数据必须使用相应备份；不要用代码回滚代替数据库恢复。

`docker compose stop` 保留容器与数据。`docker compose down` 移除容器和项目网络，但保留命名卷；`down -v` 会删除项目数据卷，不应用于普通停止或回滚。

应用通用日志位于 `/data/logs/`，补丁另将用户名、任务 ID 和提问保存为 `user_questions.log`。这份明文日志由补丁独立写入，与通用文件日志开关分离；管理员需要按业务要求管理其访问和保留周期。
