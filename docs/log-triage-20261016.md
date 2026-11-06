# 5002 日志分诊与后续处理

> 文档定位：历史诊断；严格门槛及旧来源建议已失效。本页记录当时过程；当前状态见[状态总览](current-status.md)，有效后续见[待办](roadmap.md)。

日期：2026-10-16；分支work/ldr-20261012。
范围：5002应用、SearXNG、proxy-relay三个容器的Docker stdout/stderr；回看最近30分钟的有界日志，并在北京时间11:24:45—11:26:46持续观察约2分钟。没有读取或保存用户研究原文、账户数据库内容、密钥或完整原始日志。
机器记录：log-observation-20261016.json。规则命中数不是独立请求失败次数；同一异常可在多层日志重复出现，类别也可重叠。只描述本次窗口，不代表长期稳定性或报告语义验收。

## 容器运行结论

初末三容器均running/healthy，FailingStreak=0、RestartCount=0、OOMKilled=false（针对当前容器创建之后）。
资源快照：应用CPU 0.31%、约1.073GiB内存，SearXNG约108.4MiB，relay约18.5MiB。单次快照不能证明没有资源峰值，但没有发现容器崩溃、内存杀进程或持续资源饱和证据。
因此当前不能把“日志出现在Docker里”等同于“Docker故障”，也没有依据通过重装或重启容器解决全部错误。

## 问题分类

| ID / 优先级 | 现象与证据 | 归属及确定性 | 后续动作 |
|---|---|---|---|
| L01 / P1 | 基线arXiv _get_previews有42条ERROR；Semantic Scholar _make_request有51条WARNING，样本为429/too many requests。实时窗口仍有Semantic Scholar限流。 | 外部API配额/限流已确认；重试放大和引擎选择属于应用策略优化。不是代理端口连接拒绝。 | 核实可用凭据与配额；梳理SDK/HTTPAdapter/策略三层重试，明确每任务预算和共享冷却，避免持续调用暂不可用来源。 |
| L02 / P1 | SearXNG出现DuckDuckGo/Startpage CAPTCHA、Brave限流及Google连接超时；部分请求无结果。日志显示部分搜索总超时约3秒。 | 外部反自动化限制与网络延迟；超时预算/引擎配置是部署配置问题。没有SearXNG容器退出证据。 | 核查代理出口质量、单引擎与总体超时；暂不可用引擎进入冷却并显式显示不足原因，不绕过验证码。 |
| L03 / P1 | 基线62条reference DB not yet built；journal_quality.db不存在，有.downloading标记和DOAJ/JabRef等文件。后续读数标记年龄约25分钟。OpenAlex Institutions日志在11:23:59仍推进至89,851条。 | 参考数据初始化依赖未就绪已确认；有下载进展，不能定性为线程死锁或陈旧锁。是否异常慢仍需观测分片/网络。 | 核对各源下载完成状态、分片耗时和DB构建阶段；启动检查与界面明确pending。不要把该参考库或其就绪等同于最新年度JIF已核实。 |
| L04 / P1 | 12条域名解析到private/internal IP的拦截。历史web.archive.org解析包含2001::1f0d:49a9；后续DNS复查变为其他global地址。 | DNS/网络路径异常待定位；安全模块按解析结果拦截属于设计行为。一次global地址不能证明域名解析正确。 | 对照宿主、Docker和可信解析结果，排查解析变化；修复网络解析路径，保留SSRF与DNS绑定校验。 |
| L05 / P2 | 实时窗口Wayback两次JSONDecodeError；历史Wikipedia也有一次。核对容器实际Wayback代码：只特别判断429后即response.json()。 | 上游响应异常是可能诱因；响应状态/格式处理不足是可定位的适配器代码问题。未采集响应体，不能断言其确为HTML或具体HTTP状态。 | 补非成功状态、内容格式和JSON结构校验；记录状态码/内容类型等轻量诊断，区分无结果与上游不可用，不保存全文响应。 |
| L06 / P2 | relay基线111条ConnectionResetError和8条BrokenPipeError；实时窗口8条reset。最近5次成功健康检查后0.066—0.087秒内均出现reset。 | 自有转发脚本与TCP健康探针产生的日志噪声有强时间关联，不等于代理每15秒宕机；其余连接中断仍需单独判断。 | 区分探针、无数据正常关闭和传输中断，补方向/字节计数，降低预期关闭的日志等级；保留真实传输失败记录。 |
| L07 / P2 | 日志调用Gutenberg/Gutendex等来源并出现30秒ReadTimeout；模型列表探测localhost:11434被拒，llama.cpp/LM Studio等列表也不可用。 | 引擎/提供方选择配置与不必要探测；不代表当前OpenAI-compatible模型故障。当前模型列表此前已验证200。 | 核对当前账号生效的引擎/模型配置；按任务限定可用来源，将未配置提供方探测视作不可用状态而非主模型错误。 |
| L08 / P3 | SearXNG出现10条ResultContainer.add_unresponsive_engine after ResultContainer.close。 | SearXNG上游超时收尾/并发代码路径问题；不是Docker进程崩溃。仅凭日志尚不能定位具体竞态。 | 保留复现条件，核对固定镜像对应源码与上游修复；在隔离环境验证兼容性后决定补丁或镜像升级。 |

## 不应误报的日志

- 数据库“No database found”两次发生在新实例账户初始化之前，随后新库创建、迁移0001 -> 0030成功。没有本次窗口内数据库损坏/锁死证据；不需要据此重置数据库。
- SQLCipher旧salt和Alembic启动提示需结合上述时序判断，不能单凭WARNING标记迁移失败。
- PubMed有“No abstract found”，同时有47/50等摘要获取成功记录。个别缺摘要不代表整条PubMed链路断开；缺证据的文献仍须pending。
- 原观察分类中的Connection refused匹配经核对指向可选Ollama探测11434，不能当成9876代理失效。
- 检查发现api.openalex.org仍被NO_PROXY绕过，但OpenAlex批量参考数据从openalex.s3.amazonaws.com经代理下载。前者是需整理的路由例外，不能据此断言当前参考库下载卡在直连API。
- 本次核对未发现TypeError/AttributeError/导入失败等核心Python异常模式；这不证明业务正确或不存在其他代码问题。

## 执行顺序与验收

1. P1先建立来源可用性清单、任务级冷却/重试预算和参考库进度；单独核对DNS。验收看实际成功取证、等待时间及准确失败原因，不能仅看容器healthy。
2. P2处理Wayback/Wikipedia响应解析和relay日志分类；失败返回应保留来源不可用原因，不能伪装为正常无结果。relay应验证TLS透传、正常EOF与真实断流分别记录。
3. P3再处理上游SearXNG收尾竞态及非关键启动提示。
4. 上游适配器当前来自固定基础镜像；需要部署修复时必须新增对应overlay-manifest.json项并构建测试镜像。只改旁置local-deep-research源码不会生效。
5. 针对具体改动增加必要行为验证；保留已有严格证据门禁，不因网络不稳定降低结论发布要求。

本轮只读诊断，未修改运行配置、重启容器、终止研究或推送代码。仅新增脱敏观察记录及接续说明。两分钟监控已结束，没有后台常驻监控服务。
