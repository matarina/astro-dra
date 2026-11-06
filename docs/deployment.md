# 部署、构建与回退

更新：2026-11-06。先区分本机既有5000/5002与首次部署；[旧说明原文](deployment-history-20261104.md)保留历史，不作为当前实例命令来源。[当前状态](current-status.md) · [5002说明](test-instance-5002.md)。

## 本机既有部署

| 项目 | 5000主实例 | 5002开发实例 |
| --- | --- | --- |
| 代码工作区 | `/data/ningh/nh/astro-dra` | `/data/ningh/nh/astro-dra-ui-5002` |
| Compose项目 | `local_deep_research` | `astro-dra-test-5002` |
| 配置 | 主工作区`local_deep_research/docker-compose.yml`及`compose.production.local.yml` | 主工作区根`compose.yaml`，环境文件`.env.test-5002` |
| 应用容器 | `local_deep_research-local-deep-research-1` | `astro-dra-test-5002-local-deep-research-1` |
| 镜像基线 | `astro-dra:main-20261106` | `astro-dra:subtask-scope-v3-5002-20261105` |
| 数据/配置 | 5000原数据、脚本、日志及配置挂载 | 独立`astro-dra-test-5002_ldr_data`和`astro-dra-test-5002_ldr_config` |

5002的Compose文件放在main目录，并不表示使用5000的容器或数据。代码随构建进入镜像，应用不是宿主源码热挂载。开发构建须使用UI工作区；部署沿用现有5002项目、env和卷，不能无参数启动另一项目。

## 5002开发与更新步骤

1. 在UI工作区修改实际部署补丁，查看现有未提交变化，完成对应离线/隔离验证。
2. 从该工作区用完整Dockerfile构建独立标签。下例标签需替换为本次版本，不在文档整理时执行：

```bash
cd /data/ningh/nh/astro-dra-ui-5002
docker build -f deployment/Dockerfile -t astro-dra:dev-YYYYMMDD-purpose .
```

3. 核对候选的安装文件、角色/界面及相应流程，检查没有活跃研究；记录原镜像、容器、配置和卷，按改动完成备份。
4. 在主工作区私有`.env.test-5002`中持久更新`ASTRO_DRA_IMAGE`为已验证标签；修改应保留原模型、密钥、端口、项目和卷。
5. 使用既有配置仅替换5002应用，明确禁止此步隐式从main目录构建：

```bash
docker compose --env-file /data/ningh/nh/astro-dra/.env.test-5002 \
  -p astro-dra-test-5002 -f /data/ningh/nh/astro-dra/compose.yaml \
  up -d --no-build --no-deps local-deep-research
```

6. 核对实际镜像/安装文件、登录、权限及改动相关链路，确认原卷保留，并记录5000和其他依赖未被重建。

UI-only或accounts分层构建必须明确基础镜像；不能沿用旧默认标签导致遗漏最近已部署的功能。修改Compose/deployment文件也需区分开发版本与主目录实际运行版本，合并Git不会自动同步已运行容器。

## 合入main和更新5000

11月6日已完成本次合并和5000部署，原32账号按用户要求设为普通用户，独立root另建；实际版本、验证和回退见[部署记录](deploy-main-5000-20261106.md)。下面保留后续更新方式。

5002验证完成后整理并提交功能、申请/完成合并；这一步不自动更新5000服务。合并后从main构建独立已验证版本标签，更新5000原私有`compose.production.local.yml`的镜像。沿用原项目和两份配置，仅替换应用：

```bash
cd /data/ningh/nh/astro-dra/local_deep_research
docker compose -p local_deep_research \
  -f docker-compose.yml -f compose.production.local.yml \
  up -d --no-build --no-deps local-deep-research
```

此前生产切换、原卷及备份依据见[5000部署记录](deploy-main-5000-20261028.md)。不能将5002账号/数据库复制覆盖5000；新角色功能到5000时应验证其原账号迁移和root初始化策略，5002的历史测试不自动覆盖5000数据场景。

## 配置与网络

实例有效配置以实际Compose和容器环境为准，不能把`.env`里任意变量都视作已传入容器。当前两实例默认模型为deepseek-v4-flash，事实检查开、保存前QC关、私有trace开；通用首次部署的trace默认值可能不同。

应用代理通过大小写HTTP_PROXY/HTTPS_PROXY变量，SearXNG代理在自身settings.yml，两者不是同一项配置；内部服务和模型端点按实际NO_PROXY直连。宿主代理仅监听回环时，loopback-proxy profile可用relay转发；同一网关端口不能重复绑定。5002 relay UID/GID已按宿主允许身份配置并独立固定镜像，见[连通性修复](search-connectivity-20261028.md)。

当前5002的SearXNG settings和relay脚本仍从main目录只读挂载。更新这些共享运行文件前，应核对实际使用者；普通应用代码更新使用版本镜像，不修改它们。

## 数据、回退和首次部署

更新前按改动备份私有环境/覆盖配置及相关数据库/卷，数据库一致性备份需要合适的停写窗口。代码回退恢复原镜像标签并用相同Compose项目和卷重建应用；数据库恢复是另一操作，不能靠回退镜像还原数据。旧账号权限回退限制见[账号说明](account-roles-5002-20261102.md)。

正常停止保留数据卷；不要以`down -v`作为更新或回退方式。私有trace、问题日志和实验资料不提交。当前备份目录位置见[整理核查](documentation-audit-20261104.md)，历史已删除的备份不视为可恢复。

首次部署从根`.env.example`建立私有`.env`，配置实际模型、凭据、SearXNG密钥、网络、端口与项目名，再验证Compose和构建。5000/5002已占用，不在本机直接执行默认首次启动命令。[项目README](../README.md)提供通用使用说明；新角色部署的root初始化见[账号文档](account-roles-5002-20261102.md)。
