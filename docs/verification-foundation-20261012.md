# M0 工程基础与基线记录

> 文档定位：历史基础，非当前功能已全部验收。本页记录当时过程；当前状态见[状态总览](current-status.md)，有效后续见[待办](roadmap.md)。

日期：2026-10-12；基线：115e2638fb89d643a0afb8f80134b627e6aa323a。
状态：本地工程基础完成；线上完整链路与功能阶段尚未验收。
本次将 M0 定义为基线、契约、样本和执行记录。自然语言解析界面和线上性能预算分别进入后续功能与集成阶段，避免把功能实现混入基础阶段。

## GitHub 更新核对

通过本机 GitHub 连接器现有认证读取远程 API，并拉取 Git 引用。
- main：115e263，合并 PR #1，来自 work/ldr-20261012。
- 远程工作分支：f9eb8c4；本地工作分支原为同提交，工作区干净。
- f9eb8c4 新增通用 Compose、固定镜像部署、补丁安装清单、工程计划和维护文档；无验证 Python 逻辑变更。
- 文件内容确认一致后，本地 work/ldr-20261012 已快进至 origin/main 的 115e263；未推送，本地 main 未切换。
- 影响：后续构建优先使用根目录 deployment/Dockerfile；新增 research_verify 文件由现有 COPY 自动包含。生产部署仍使用旧 local_deep_research Compose，不能直接用新 Compose 替换并假定复用数据。
- 初次 git fetch 因认证失败，已通过现有连接器认证完成核对；凭据未写入仓库或输出。

## 实测基础

现有验证测试：55 passed（0.33s），Python 3.14.7。
依赖：pytest 9.1.1、pytest-asyncio 1.4.0、respx 0.23.1、pydantic 2.13.5、pydantic-settings 2.15.0、httpx 0.28.1、loguru 0.7.3。
命令：

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=local_deep_research /data/ningh/nh/verify-venv/bin/python -m pytest -q -p no:cacheprovider local_deep_research/tests

生产容器：local_deep_research-local-deep-research-1，healthy。
实际镜像：sha256:e94a4b527a6f61778da2aa7b2994722562fbfadac0dda9c6b499f64a16a5b1b2。
镜像标签：localdeepresearch/local-deep-research:astro-dra-d7d874b。
Compose 工作目录：/data/ningh/nh/astro-dra/local_deep_research。
通用构建基础 digest：sha256:ce95481a35d3eebc2c1ae7bd34fad426108c3fb8d1a22f66c9e772276869c2f0。
生产镜像 ID 与构建基础 digest 用途不同，不视为同一制品。
历史通用镜像启动记录见 verification-20261012.md，本次未重复构建或重启。
依赖尚未完全锁定；记录实测版本不等于实现完整依赖锁定。

## 契约与固定样本

新增 research_verify/contracts.py：TaskPolicy、JifSnapshot、CheckResult、EvidenceLocator、ClaimEvidence 和 evaluate_gate。
旧模型不迁移，当前生产逻辑不接入新契约。
- 必需检查全部 pass 才 admitted；明确 fail 为 rejected；缺失/unknown/not_applicable 为 pending。
- 重复检查结果或空规则为 pending；规则明确范围，结论支撑通过不等于四需求全部通过。
- 原文引用定位包含文献ID、artifact、哈希、章节/页码、字符区间和全文/摘要/片段依据。
- supported 的结构必须带已验证短引与一致文献ID；布尔字段不自行证明引文真实，后续核验器必须计算 quote_verified。
- TaskPolicy 保留比较符、精确年份、JIF版本和正文关键词规则；无已确认 JIF 版本时不编造年份。
- 原文哈希基于指定 artifact 的规范化文本；偏移以同一字符串的 Python 字符索引为准，后续明确规范化版本。
固定验收规格：tests/fixtures/strict_verification_cases.json，14 条人工编写的合成正反例。
这些样本是后续检测目标，不是已实现的在线验收；真实语义准确性仍需要真实文献人工标注集。

## 报告出口审计（源码级）

1. 策略 _finalize：产生 findings.content、formatted_findings、current_knowledge；QC 主要作用于 formatted_findings。
2. current_knowledge 会追加 QC 表，但未使用同一个经修订的最终正文；findings.content 仍是 synthesized_content。
3. 普通保存：research_service._extract_synthesized_answer 优先 Final synthesis，随后 current_knowledge；再执行 _compact_citations 和超链接转换，写入 report_content。
4. 详细保存：IntegratedReportGenerator.generate_report 生成新报告，随后独立整理引用并写入存储。子章节 QC 不能替代最终报告 QC。
5. 展示与导出：旁置上游 routers/research.py、history.py 通过 report_assembly_service.assemble_full_report 装配；导出调用 export_report_to_memory。聊天路径读取正文。
6. 引用整理发生在策略 QC 之后，可能改变编号；溯源应使用稳定 paper_id，并携带原编号到最终编号的映射。
7. 部署清单仅覆盖五个既有补丁；如修改 report_generator、routers 或 assembly_service，须新增清单项并验证固定基础镜像接口，不能只改旁置上游源码。

审计为源码证据；完整模型研究、详细报告和各格式导出未在本次运行验收。
优先阶段必须覆盖普通保存和详细报告最终保存出口，异常不能回退保存未核查原文。

## 后续首阶段：结论可溯源

先支持从可获得原文中定位证据，明确 basis；摘要仅能支持摘要明确包含的主张，不能冒充已打开全文。
原文获取失败、身份无法对应或缺少引用时为 unverifiable，不作为已核验事实发布。
先做逐引用映射、原文短引存在性、未引用结论检测与统一发布控制；随后接语义判定与有限修订。
当前阶段通过只表示结论证据核查通过，不证明 DOI、JIF 或正文关键词符合全部要求。

## M0 完成验证

新增22项契约行为测试，合计77 passed（0.37s）；命令同上。
验证范围：必需项聚合、未知/缺项/重复结果不准入、结论检查范围隔离、规则默认值与非法参数、证据定位字段和文献一致性。
14条合成验收规格均已备齐，但检测语义和目标规则的测试留待 M3-A/M1/M2，不计入本次77项通过声明。
git diff --check 通过；新 Python 文件 AST 校验通过；JSON 中14条规格可解析、ID唯一；文档入口已检查。
发布契约设计：draft（草稿）、withheld（无足够可发布证据）、partial（仅部分结论核验可发布）、traceability_checked（仅结论证据核查完成）、strict_verified（四需求及完整报告出口均验收通过）。
发布状态不能仅由模型判定或本文契约字段生成，须后续发布控制器结合原文短引核查与结论覆盖计算；当前未接入。
本次成果提交标题：Add verification foundation and prioritize claim traceability。
