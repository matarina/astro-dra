# 5002 开发测试实例

更新：2026-11-05。[当前状态](current-status.md) · [构建与更新](deployment.md) · [旧时间线原文](test-instance-5002-history-20261104.md)。本说明只对应5002。

## 实例定位

| 项 | 当前对应 |
| --- | --- |
| 开发目录／分支 | `/data/ningh/nh/astro-dra-ui-5002`，`work/ui-5002-20261028` |
| 应用容器 | `astro-dra-test-5002-local-deep-research-1` |
| Compose项目 | `astro-dra-test-5002` |
| 实际Compose | `/data/ningh/nh/astro-dra/compose.yaml` |
| 私有环境文件 | `/data/ningh/nh/astro-dra/.env.test-5002` |
| 镜像基线 | `astro-dra:subtask-scope-v3-5002-20261105` |
| 端口 | 宿主5002 → 容器5000 |
| 数据卷 | `astro-dra-test-5002_ldr_data` |
| 配置卷 | `astro-dra-test-5002_ldr_config` |
| 搜索／代理 | `astro-dra-test-5002-searxng-1`、`astro-dra-test-5002-proxy-relay-1` |

5002已具备最新工作台、中文、三主题、侧栏和账号角色；这些新增代码已于11月6日合入main并部署5000，见[部署](deploy-main-5000-20261106.md)。修改开发目录不自动改变5000；必须从开发目录构建候选，并沿用上表配置只更新5002。用户已有账号和研究记录保存在原卷中。

2026-11-05已部署第三版，13:48:57重建应用后healthy/HTTP200；保留有界搜索/独立交付，增加同源正文恢复、范围内待查问题及写作前原文主体阅读。核查函数和原开关未改，新阅读默认开启。详见[部署和测试](subtask-scope-v3-deploy-5002-20261105.md)。

## 只读管理入口

```bash
docker compose --env-file /data/ningh/nh/astro-dra/.env.test-5002 \
  -p astro-dra-test-5002 -f /data/ningh/nh/astro-dra/compose.yaml ps

docker compose --env-file /data/ningh/nh/astro-dra/.env.test-5002 \
  -p astro-dra-test-5002 -f /data/ningh/nh/astro-dra/compose.yaml \
  logs --tail=100 local-deep-research
```

原始日志可能包含私有任务资料，排查时按任务和必要字段读取。构建、替换与回退命令统一维护在[部署说明](deployment.md)，本页不再堆叠每轮旧镜像的重启命令。

## 参数与验证

默认deepseek-v4-flash、langgraph-agent、PubMed/SearXNG/Europe PMC；12/6、500候选、事实检查开、保存前QC关、自动全文默认关、私有trace开。普通用户界面不提供模型/引擎覆盖；管理员保留相应能力。功能使用方式见[账号角色](account-roles-5002-20261102.md)。

最新第三版465回归通过，部署后五目标SHA对应、healthy/登录200；实际容器读写核查/失败回退通过，同镜像新检索27来源/24引用，质量限制见[部署测试](subtask-scope-v3-deploy-5002-20261105.md)。87文件/403回归为此前基线。研究质量、登录持久性、检索长尾和纳入条件尚未全面解决，见[待办](roadmap.md)。隔离预览、测试账号和真实模型验证要明确区分，不能在此实例运行只适用于可丢弃数据的测试脚本。
