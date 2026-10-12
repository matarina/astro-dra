# 源码与补丁维护

本仓库保留两份具有不同用途的代码，不合并同名目录，也不删除原始文档。

`local-deep-research/` 是旁置上游项目，使用 `src/local_deep_research/` 的标准包布局，带有自己的 `pyproject.toml`、`pdm.lock`、前端工具链和测试。其源码与基础镜像可能存在版本差异。若从这份源码开发运行，需要在该目录按上游 README 建立独立环境，并自行完成前端构建和 Python 安装；根目录的测试依赖不包含完整应用依赖。

`local_deep_research/` 是部署补丁目录，不是可以直接启动的完整 Python 应用。`deployment/Dockerfile` 从已捕获的运行镜像安装补丁，映射统一定义在 [overlay-manifest.json](../deployment/overlay-manifest.json)：

| 补丁 | 安装目标（相对应用包） | 目的 |
| --- | --- | --- |
| `research_service.py` | `web/services/research_service.py` | 用户提问日志、报告引用整理 |
| `langgraph_agent_strategy.py` | `advanced_search_system/strategies/langgraph_agent_strategy.py` | 搜索结果去重和核验入口 |
| `overlay/tracker.py` | `web_search_engines/rate_limiting/tracker.py` | arXiv 请求间隔处理 |
| `search_engine_serper.py` | `web_search_engines/engines/search_engine_serper.py` | 查询引号处理 |
| `search_engine_pubmed.py` | `web_search_engines/engines/search_engine_pubmed.py` | PubMed 查询引号处理 |

`research_verify/` 安装到解释器的 site-packages 根目录，作为独立包使用。补丁安装脚本通过活动解释器定位目录，先检查全部源文件语法和目标存在性，再复制；不依赖硬编码的 Python 次版本路径。目标存在性不证明接口兼容，新基础镜像仍需完整研究联调。

修改部署行为时，应修改补丁并重建根目录镜像；修改旁置源码时，应明确后续采用源码构建还是将变更移植到部署补丁。当前没有自动同步流程。旧 Dockerfile 的 `latest` 构建方式只为保留历史部署而保留。

新增核验能力以 [严格核验工程计划](ldr-verification-engineering-plan.md) 为验收依据。`research_verify/README.md` 的模块说明描述当前标注式实现；旧需求文档中的完成状态不代表严格流程已实现。

根目录 `requirements-test.txt` 仅包含独立核验测试所需依赖，带版本范围，尚未作为完整依赖锁文件。当前 Docker 构建固定上游镜像 digest 和额外 `ddgs` 版本，其传递依赖仍由 pip 解析，因此不宣称逐位可重现。
