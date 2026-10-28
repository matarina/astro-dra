# M3-A 第6项：真实报告与出口验收

日期：2026-10-16；分支work/ldr-20261012；第5项本地提交bfb2e00。
状态：进行中。自动化通过不等于语义人工对账通过；本文件在最终复核完成前不能作为验收通过证明。

## 已执行的真实流程

真实配置deepseek-v4-flash，temperature=0；使用现有SourceBasedSearchStrategy和IntegratedReportGenerator。
PubMed实时取证，普通/详细最终发布，临时SQLite与文件备份实际回读，展示装配及Quarto/LaTeX/ODT/PDF/RIS导出。
不使用生产数据库，不创建生产HTTP研究任务，不重启生产。
普通/详细生成已多轮实际执行；结果原始证据按abstract标注，不能视为完整全文或四需求严格通过。

自然检索场景出现错引：报告写STEP1数据却引用综述等不含所述数据的文献，正确阻止发布。
定向正例用PMID33567185限制候选集合，仍实时调用PubMed原引擎；这是受控真实文献验收，不是无约束检索成功率评估。
此前PubMed只返回片段、最终复核整篇扣住及Quarto链接转换问题均已修复，详见第5项记录。

## 自动检查与内部逐句复核的差异

| 文件 | 自动检查 | 内部源文对照 | 处理 |
|---|---|---|---|
| publication-e2e-20261016-accepted.json | false：数字负例因内部PMID删除而跳过 | 11条中2条误支持 | 保留第一轮review，补DOI识别、推断拆分、分析名称核对 |
| publication-e2e-20261016-reviewed-final.json | true | 9条中2条仍有未确认的分析解释 | 第二轮review；完善so/meaning等连接句和不带固定后缀的分析术语 |
| publication-e2e-20261016-v2-final.json | true | 6条中1条计数改写丢失终点、表述不完整 | 第三轮review；补结局人数范围检查，冻结既有生成句子回归 |

review-20261016-first/second/third记录使用claim_sha256关联，不缓存整篇论文；审核为代理内部对照，不是独立领域专家裁决。
不要根据文件名accepted/final认定通过；必须同时看自动检查和review结果。

## 修复与回归

- 独立的显式分析名称规则：来源未给出名称时不能认证模型自行命名；包括intention-to-treat effect等非固定语法后缀。
- 机制隔离/中介等额外断言需要自身证据，不能从入组条件推出。
- 推断连接句需拆分并逐个复核，重写只保留明确报告的观察或设计，不加入派生分析比较。
- 人数/比例保留对应的终点、组别、分母和时间，不能把达到终点的子集人数改成样本量。
- 新增规则以独立rule检查追加，不覆盖原始模型的mismatch/uncertain。
- 全量265 passed（0.83s）。合成控制测试与真实文本对账分开统计。
- Docker依赖层移到代码COPY前，避免每次规则改动都重新下载依赖；完整依赖锁定仍未完成。最近一次lxml索引临时失败已记录；v3重试构建已成功，manifest sha256:32f584e7487f787d0afededd25f456a683453e2543669d28431217e1045b6428。

## 固定回归与最终复验（待完成）

fixtures/frozen_generated_report_cases.json冻结此前公开论文试跑生成的断言，包括已知反例；不含PubMed完整摘要缓存或生产用户数据。
回放仍需实时取得PubMed摘要、调用真实模型、执行最终发布与所有存储/导出检查。它是既有生成输出的回归，不冒充重新生成研究。
最终应同时记录固定生成报告回放与现有流程真实研究复跑；普通/详细至少保留可对账事实，四类故障不能回退发布旧草稿，三类已知误判反例不能完全支持。

复跑示例（镜像构建成功后，输出不能覆盖既有文件）：

    scripts/run_publication_e2e.py --image astro-dra:traceability-20261016-v3 --paper-scope 33567185 --replay-generated --output docs/publication-e2e-20261016-frozen-final.json
    scripts/run_publication_e2e.py --image astro-dra:traceability-20261016-v3 --paper-scope 33567185 --output docs/publication-e2e-20261016-live-final.json

## 完成边界

完成条件：最终代码回归与构建、真实正例和故障回归、逐条内部原文对账、记录限制及可回滚提交。
仍不代表零幻觉或大样本泛化能力；数量少、单篇临床论文摘要、保守规则可能漏保留正确结论。
HTTP登录/浏览器交互、真实生产用户任务、全部策略线上运行及领域专家验收留给后续上线/M4；本项不得宣称这些已验收。
正式文献身份、年份/语种/JIF严格准入、正文关键词属于M1/M2及M3-B整合，仍待执行。

## 本次状态核对

固定回放publication-e2e-20261016-frozen-final.json已完成，checks_passed=true，普通5条、详细3条、8处短引定位；数据库/文件/展示回读、两类报告的五种导出、4类故障、3类限定信息反例均通过。运行178.139秒，34次成功模型回复；未统计失败调用总数。
此文件generation_mode=frozen-generated-report-replay、search_iterations=0；scope字段保留了旧的策略/生成器描述，是日志标注缺陷，不能据此声称本轮重新生成研究。当前未补回放最终8条的内部逐句复核，自动通过不能单独作为第6项完成依据。

真实策略/详细生成器复跑输出publication-e2e-20261016-live-final.json；运行已结束（316.669秒，51次成功模型回复）：普通withheld、0条，详细partial、5条，checks_passed=false。普通7条原断言均pending，原因包括semantic_uncertain、quote_not_found和missing_citation。详细5条逐条与实时摘要短引对照一致，见publication-e2e-review-20261016-live-final.json；这是代理内部复核，不是独立专家验收。

实际数据库/文件/展示回读及五种导出均完成；普通withheld没有精选来源，因此其RIS允许为空。详细报告五种导出非空，引用URL和Quarto正文核对通过。四类故障均withheld，三类限定信息反例均未完全支持。最终逐字短引定位5处。

第6项仍未通过：必须先定位普通报告为何未保留事实，再补真实正向验收；不能以详细报告单路径通过、固定回放通过或故障成功拦截替代。当前模型与启发式可能漏保留正确结论，只有摘要，未做全文、浏览器/生产HTTP及独立领域审核。本次未改生产、未推送；GitHub认证不可用，远程实时状态仍未知。
