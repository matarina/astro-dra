# 结论溯源语义试跑（2026-10-14）

状态：基线试跑完成，未修改核查算法、未部署。
应用代码基线：0cdbc6e；分支：work/ldr-20261012。
范围：当前分支 CitationQc + 真实模型端点 + 15条受控合成样例，不是完整研究报告，也不是真实文献准确率验收。

## 环境和复跑入口

5000生产实例配置可达，端点 /models HTTP200，提供当前配置标识 deepseek-v4-flash。
本次使用该端点的生成模型配置作为 judge，temperature=0；模型标识为请求中的配置名称，不据此证明服务后端模型权重身份。
5001测试实例使用示例端点和模型名称，未用于本次验证。
没有创建生产研究任务、修改服务配置或重启容器；仅调用模型接口处理合成文本。
GitHub远程已认证拉取，origin/main仍为115e263，无新增主分支提交。

复跑（输出路径必须使用新名字，避免覆盖历史结果）：

    PYTHONDONTWRITEBYTECODE=1 /data/ningh/nh/verify-venv/bin/python -u scripts/run_semantic_pilot.py --output docs/semantic-pilot-NEW.json --workers 2 --timeout 60

样例：local_deep_research/tests/fixtures/semantic_pilot_cases.json。
逐条JSON：semantic-pilot-20261014.json，包含模型原始回复、判定、短引定位和时间。
脚本在内存读取现有容器凭据，不保存或显示API密钥；只允许明确标注 synthetic 的样例。

## 实测结果

| 指标 | 结果 |
|---|---|
| 样例数 | 15（3正例，12个不应完全通过的样例） |
| 判定与预置标签完全一致 | 13/15 |
| 正例 supported | 3/3 |
| 非正例被错误判为 supported | 1/12 |
| 模型请求 | 14 |
| 网络或HTTP错误 | 0 |
| 模型试跑墙钟耗时 | 3.33秒，不含准备、授权与报告整理 |
| 模块回归 | 143 passed（0.48s） |

样例预置标签由工程代理编写，并非独立领域专家裁决。不能将上述小样本比例宣传为真实科研文献的泛化准确率。

## 关键问题：相关性被误判为因果（N04）

报告结论：

    Higher marker M causes increased disease risk [1].

供应原文：

    In an observational cohort, higher marker M was associated with increased disease risk. The study did not establish causality.

预期 unsupported，实际 supported。
模型理由认为“association”与结论措辞一致，返回真实存在的相关性短引；程序确认短引存在后保留了 supported。
这说明原文短引存在性已被检查，但未能阻止语义强度升级。原文中“不建立因果”的限制也没有触发确定性拦截。
这是本轮明确的错误完全通过，必须优先补上因果强度/研究设计核查。

## 另一处标签差异：多引用含不相关来源（N11）

预置标签为 unverifiable，实际 partial。
逐篇结果为：第一篇 supported，第二篇 unsupported，聚合器按既有规则输出 partial。
未出现“整条完全支持”的误通过。这处差异涉及“不相关证据应为 unsupported 还是 unverifiable”的判定口径及预置标签，不与N04同等计为事实误通过。
未来验收应分别统计“标签完全一致”和“不应完全通过却完全通过”；partial/unverifiable都不能直接作为严格发布通过状态，最终发布控制仍未实现。

## 本轮通过的受控样例

数字改写、方向反转、否定词丢失、动物外推人类、单位错误、中英文数字不一致，均未判为supported。
范围外推、复合结论仅一部分有支撑，均返回partial。
无引用与错误引用号均返回unverifiable；正文后部证据和正确相关性陈述均返回supported。
这仅说明各单个受控样例表现，不证明这些风险类别已被可靠解决。

## 下一步优化

1. 在逐篇判定中显式核查因果强度和研究类型，保留具体证据与限制语句；用N04作为必须不再误通过的反例。
2. 对原文明确否认因果或临床验证的情况增加可解释拦截，不允许只凭模型supported或短引存在升级为通过。
3. 增加同类正反例及复合结论拆分，再做真实文献人工对账；统一unsupported/partial/unverifiable的标注口径。
4. 在后续最终保存出口中删除/修订或阻止未核验主张作为已证实事实发布，确保普通/详细报告一致。
5. 不把一次temperature=0试跑视为稳定性证明；优化后保留新旧结果，按同一固定样例比较。

本次新增仅为试跑脚本、合成样例和结果记录；生产核查算法未改。
提交标题：Record real-model semantic pilot and causality failure。
