# LDR 开发接续记录

## `local-main` 合入 `main`（2026-11-10）

按用户要求，在现有 `main` 上保留 `local-main` 的当前树，并记录 `origin/main` 历史为合并提交 `dc44449`。随后将合并后的 `main` 推送到远程，并删除远程 `local-main`；本地没有单独的 `local-main` 分支可删。提交时无已跟踪改动，未部署或修改应用代码；验证时发现一个未跟踪的用户归档文件，未触碰。

## README English update (2026-11-10)

Replaced the root README with an English version, added the repository banner at `assets/banner.png`, and aligned the evidence-workflow description with the current PubMed/SearXNG/Europe PMC flow. No application code, deployment configuration, user data, or running services were changed. `git diff --check` and the banner/link checks passed. The changes are local and uncommitted; no deployment or remote push was performed.

最后整理：2026-11-04。此文件保留短接续信息；完整历史已按原始字节保留，见文末。当前事实集中在[当前状态](current-status.md)，后续任务集中在[待办](roadmap.md)，所有记录见[总索引](README.md)和[完整目录](document-catalog.md)。

## 开始开发前

1. 读取当前状态、待办和本文件最近一条记录，再按任务查阅[当前流程](current-research-flow-20261016.md)、[源码布局](source-layout.md)、[部署说明](deployment.md)。
2. 重查两个worktree的Git状态、容器实际镜像和部署入口。11月6日功能已提交合入main并部署5000；后续仍重查是否有新未提交变动。5002代码开发在UI工作区，运行配置在主工作区。
3. 先在5002开发验证，再整理合入main；5000更新单独执行。当前先做文献真实性、检索证据质量和报告准确性等核心优化，登录及开发工程问题后续处理。旧严格工程计划和旧接续中的“下一会话任务”只作历史依据。

## 合入main、推送GitHub并更新5000（2026-11-06，已完成）

按用户要求，以简短信息“同步5002界面、权限与研究流程”提交b2f2848，172文件，快进合入main并通过GitHub连接器非强制推送。保留main完整README，原未提交内容有私有备份及stash。远程tree/完整提交对象与本地一致，Git CLI认证仍缺失；UTC重建对象未匹配时未移动分支，按实际+0800复核后完成。

465回归2.72秒、模型选择与18份JS语法通过；复制32账号的无网络原生迁移/HTTP测试通过。仅清理报告模板五处空白，Jinja通过；候选基于5002最终9258c8da…，90目标计入Agent/账号转换后匹配。17:14:07部署5000为main-20261106/77df4c68…、容器9b2fcf84…，healthy/登录/root审批200，默认Flash实际短调用通过，启动ERROR0。仅镜像和子任务预算4→8变化，原模型/凭据/端口/卷保留，5002/搜索/relay/5018 ID及启动不变。

停服一致性备份8,987,402,240字节/15,570条目，112原加密/相关文件前后SHA全同。原32账号全部user，管理员0，另建独立root，总33；32迁移审计/完整性检查通过。原密码及研究数据不改、不解密。root密码只在私有0600文件；旧镜像和回退配置保留。详见[部署及验证](deploy-main-5000-20261106.md)/JSON；私有资料ldr-experiments/merge-5002-main-5000-20261106。

没有完整新研究或全量历史导出复测；原检索异常、搜索页入引用、核查覆盖/漏判、登录持久性仍未解决。不把上线和原文保全当准确率验收。文档/目录同步后另提交部署记录；下一步按核心待办定位有效检索和引用身份/语义问题。

## 5002与main/5000累计对比（2026-11-06，只读核对）

按用户要求核对实际两容器和工作区，5000仍84ea05a4…/main-20261028，5002仍9258c8da…/subtask-scope-v3-5002-20261105，均healthy。三包代码/模板/资源841对857文件，810相同、31修改、16新增、0删除，共47差异；完整路径/SHA见[累计对比](5002-vs-5000-20261106.md)/JSON。增量为工作台/中文/主题侧栏、角色审批/统一配置、子任务原文交付/预算收尾/过程及写作前原文主体阅读；另列构建/测试/代理修复，未把早已合入的三源/500池/核查/publication/trace重复算新增。

实际AST确认evidence_flow只有synthesize变化，核查函数保持；5000环境子任务上限4，5002默认8（7搜索＋1交付），不能只看构造函数默认或Git提交数。GitHub只读compare确认远程main仍e9be103，CLI fetch仍认证失败；新增功能未提交合并。新增两份对比文档及导航，文档201文件/当前链接/JSON与diff检查通过；未新跑回归/研究/模型、读取用户库、修改应用/环境或重启。昨天检索/引用/核查覆盖及登录/准确性未决保持；5018另一个验证镜像不计入5002。

下一步按用户选择处理未决项或整理合并；不因比较请求自动部署5000，不将已部署视为语义质量全部通过。

## 第三版部署5002与实测（2026-11-05，已部署重启）

按用户要求将最终测试镜像9258c8da…原样部署为astro-dra:subtask-scope-v3-5002-20261105，13:48:57新e6291b1b…启动，healthy/入口和登录200/启动ERROR0；五文件安装SHA与465回归最终版本一致。原项目/环境逐键值/挂载/端口保持，5000/搜索/relay ID和启动不变；备份后仅env镜像行变化，原报告/用户库不改。

实际容器UID1000模拟读取→写作→原生核查及读取超时回退通过，42trace权限/SHA通过。另同部署镜像/环境/网络、无生产卷的真实新检索368.404秒完成，27来源/24引用，34阅读原句逐字匹配来源、260快照SHA通过；原文阅读/原生核查实际开启。LRRC4缺失后果方向正确，但完整机制链未写出，不能验收原错误已稳定消失。两子任务7轮均空检索、partial无材料，14个Writer来源为PubMed搜索页；一组核查因预算未执行，另一组9issue/0修订，不当作全部核查通过。

旧V2/新V3同配置查询对照均三源0结果；见PubMed HTTP500/缺idlist、Europe PMC503和SearXNG Bing超时，未建立新版独有回归，不把接口错误当无相关文献。未进一步改检索/核查或默认模型；四个独立测试容器保存资料后清理，镜像保留。详见[部署测试](subtask-scope-v3-deploy-5002-20261105.md)/JSON；私有资料ldr-experiments/subtask-scope-v3-deploy-5002-20261105。未提交推送合并，fetch认证仍失败。

下一步定位有效检索/错误表达和搜索页入引用，再测子任务新材料及完整关系；核查覆盖/语义漏判单独处理。新版读取不是核验通过，不增加自动删句或硬性发布门槛。

## 第三版选段/范围/原文主体阅读候选（2026-11-05，已改测试，未部署）

按用户要求先复现后逐项修改：同源有界窗口/唯一长原文字串恢复正文，保持未定位引句标记；gap改为子任务范围内待查问题，兼容旧未核实说明；Writer获得实际选入材料范围，明确标注的草稿解读作为阅读问题，原稿/引用/普通正文/表格保留；新增source_reading，先选连续原句及其主体/状态，再按原文主体分组供写作。每批最多一次读取调用、24篇/24000引句字符，失败仍供原文继续写作，无报告门槛。默认会增加模型调用/延迟。

465回归通过（新增23），原34卡回放逐字一致，来源19无需改模型输出即恢复4908正文，总23214<24000；候选942文件仅5辅助模块变化，UID1000离线图执行/trace权限通过。最终默认模型实际读写两次固定42来源/原草稿，68.548秒，目标LRRC4/范围断言两份未复现；74条原文记录与供给及原字段完全对应，32事件SHA通过。先前仅加提示、提纲、解读边界或平铺笔记仍有反转/范围扩大，均保存；最终有限样本不当作总体语义验收。

evidence_flow仅synthesize定义改变，原核查函数/开关未改；已向用户澄清本轮是否纳入核查，未收到答复前不做依赖修改。候选9258c8da…未部署，当前5002仍90cc95ab…，5000/运行环境/卷/原报告不变；未解密用户库、提交推送合并，fetch仍认证失败。详见[第三版记录](subtask-scope-v3-20261105.md)/JSON；私有全部产物ldr-experiments/subtask-scope-v3-20261105。下一步确认核查范围后部署观察，新阅读记录不等于事实核验通过。

## 第二版真实任务0fee90a3复查（2026-11-05，只读分析）

新版90cc95ab…用户任务08:50:57–08:56:16完成，3/3子任务交付（治疗7轮自然、遗传6轮自然、机制7轮后独立收尾）；16trace/179快照字节/SHA一致、34卡逐张对应自己来源。42总来源/42Writer/39书目。LRRC4完整摘要供给Writer且最终方向正确，但未进入子任务卡/主草稿，不能用此证明子任务已稳定压缩该机制。

仍有三类具体问题：机制summary的“同模型无机制互动证据”过宽；遗传来源19删Table2/Fig3后的引句不连续，正文118240字符已取得却回退1552摘要，丢基因段细节。只改诊断选句的离线build_handoff回放可返回4908正文上下文，总23214<24000，证明是定位/回退路径，不是预算。另“摘要未提供结局”在主草稿/最终扩大为“多数研究未报告”，核查claim31/source11用“治疗很少持久恢复功能”判supported，0修订；核查漏判仍在。

详见[复查与边界](subtask-handoff-live-0fee90a3-20261105.md)/JSON；私有全部过程和回放ldr-experiments/subtask-live-review-0fee90a3-20261105。辅助查看脚本role/type兼容错误已修，应用未改；未新调用模型、重跑研究、修改配置/报告、解密用户库或重启，fetch仍认证失败，未提交合并。下一步分别讨论子任务选段/缺口、写作范围及核查支撑判定，不将收尾成功视为语义全部解决。

## 子任务第二版部署5002（2026-11-05，已部署重启）

按用户指令，将昨日最终测试镜像90cc95ab…原样加部署标签astro-dra:subtask-handoff-v2-5002-20261105。源码/测试SHA与442回归记录一致；UID1000断网实际图/工具双任务预算交付、来源隔离及0700/0600权限通过。可见3项研究均结束；原env/Compose/运行资料私有备份，候选Compose仅image变化。实际env仅更新ASTRO_DRA_IMAGE，沿原项目/卷no-build/no-deps重建应用。

北京时间08:38:14新容器bc70fe3d…启动，healthy、入口/登录200、启动ERROR/Traceback0；新控制器已安装并接入Agent，三目标安装SHA匹配，核查/共享generation/原trace不变。环境逐键值/挂载/端口保持，5000/搜索/relay ID及启动不变。Env列表直接比较因顺序不同失败，逐键值确认一致；文档补丁整行匹配失败后修正，无应用改动。没有新真实研究/模型调用，未读取解密用户库或重写历史报告；未提交合并，fetch仍认证失败。

见[部署与回退](subtask-handoff-v2-deploy-5002-20261105.md)/JSON，私有产物ldr-experiments/subtask-handoff-v2-deploy-5002-20261105。原env可恢复回第一版，卷无需变更。下一步观察新任务的实际交付与报告质量，再单独处理核查；部署健康不代表总体语义问题解决。

## 5002任务62827275监控（2026-11-05，旧版运行、只读）

跟踪用户新任务08:24:23–08:30:38完成，实际5002仍为第一版84c1b5fd…/c4783450…，新控制器未安装。3子任务83.862/87.371/96.995秒均GraphRecursionError、没有消息/作业；主任务继续用105共享来源，76条进入Writer、最终51书目。LRRC4原102/展示8完整摘要实际供给，草稿/Writer/最终该句均把保护作用归于LRRC4本身，本轮反转未复现；不能归功于未部署的第二版，也不能说明语义问题稳定解决。

19trace/100快照字节/SHA全通过，全部recorded；5组核查/33单元、54条issue均supported，0修订，非独立质量验收。1次Loguru重入错误保留；旧版缺失败前子任务逐轮/token，不能断言上下文超限。详见[监控记录](subtask-handoff-live-62827275-20261105.md)/JSON，私有产物ldr-experiments/subtask-live-review-62827275-20261105。未新增模型调用、重跑、读取解密用户库、修改应用/配置/报告或重启；fetch仍认证失败，未提交合并。下一步部署第二版再观察新任务，核查另做。

## 子任务第二版（2026-11-04，已优化测试，未部署）

在5002开发工作区实现有界搜索＋独立无工具交付：默认8次模型决策分为最多7轮搜索和1次收尾；自然完成则复用交付。按子任务隔离记录来源/更新，逐步保存消息、轮数/长度/token元数据；迭代异常/普通错误保留材料并尝试收尾，交付失败则返回真实原文和partial，取消向外传播。总结改为方向/论文用途/结构/缺口导航；原文沿用真实来源定位和预算标记，无题目规则。核查/共享generation/原trace哈希未变。

最终442回归通过；真实LangGraph/工具线程双任务预算交付、来源隔离和941文件仅三处变化检查通过。新检索全流程第一候选389.01秒，5/5子任务交付、64来源/41引用、46原文卡及255trace逐字/区间/SHA核对通过；该报告未涉及LRRC4，不算原问题语义验收。之后仅补跨轮重复tool_call_id兼容，最终镜像90cc95ab…完成回归、实际图测试和两篇原文真实模型回放：1自然＋1收尾交付、4卡/31事件完整，有限阅读LRRC4方向正确。完整新检索未在最终微调镜像上重跑；bridge代理失败测试保留，不当通过。

详见[第二版与测试边界](subtask-handoff-v2-20261104.md)/JSON。私有产物ldr-experiments/subtask-handoff-v2-20261104。5002仍运行第一版，未重启/改环境/用户库或历史报告，5000/搜索/代理不变；未提交推送合入main，fetch仍认证失败。下一步部署后观察实际用户任务，再另做核查；原文保全与小样本正确不代表总体幻觉问题解决。

## 子任务退出原因补查（2026-11-04，仅诊断与方案）

核对实际LangGraph out_of_steps分支：GraphRecursionError为未达到停止条件前步数耗尽，不等于检索零命中，也非1800秒超时。三子任务86.296/111.597/138.403秒结束；执行窗口50条PubMed原始检索日志中39有命中11为零（含重叠主任务查询、筛选前结果，不等于子任务精确轮数/有效论文数）。未发现上下文超限报错，但缺失败前输入/token，不能排除间接影响。默认8轮/2×+1图限制已确认，实际任务覆盖值未记录，不冒称已捕获配置。

方案是有界搜索＋独立有界交付，搜索将尽时关闭工具并用已有材料整理，失败仍返回原始材料和partial状态；过程中保全消息/按子任务来源及预算/长度。暂不简单加大上限，核查仍按用户方向另做。细节追加[实跑记录](subtask-handoff-live-4926df11-20261104.md)，私有iteration-analysis.json；没有改应用、配置、模型/报告或重启，未新增模型调用。

## 新版真实任务监控（2026-11-04，问题未解决）

只读跟踪用户任务4926df11…，15:28:52–15:37:08完成保存。96快照字节/SHA全通过、无省略；3子任务均GraphRecursionError，未到invoke后交付/消息记录，subtask_handoff=0。共享来源仍保留109条，85条进入Writer，LRRC4原109摘要与旧轮逐字一致且完整供给；主草稿/Writer仍将保护作用归给缺乏状态，核查claim18判supported，0修订，最终展示23仍错误（62书目）。

不能把错误只归于子任务总结；本轮未交总结时主写作仍出错。第一版未覆盖迭代失败的收尾与材料保全路径，正常路径小样本成功不能当真实问题修复。详见[监控结论](subtask-handoff-live-4926df11-20261104.md)/JSON，私有全产物ldr-experiments/subtask-live-review-4926df11-20261104。本轮无应用/配置/报告修改、无重跑/新模型调用/重启，未解密用户库；Git fetch仍认证失败，无提交推送。下一步先补可靠收尾/异常过程记录，再分别处理主写作与核查，不自行加题目规则。

## 子任务交付第一版部署5002（2026-11-04，已部署重启）

按用户要求将已验证版本部署到5002并重启应用。原accounts实际镜像ID分层，仅Agent＋新增subtask_handoff两处包文件变化（940文件比较）；断网临时镜像下ldruser双子任务交付/trace/SHA/权限检查通过。沿原项目/Compose/卷，仅env的ASTRO_DRA_IMAGE改为astro-dra:subtask-handoff-5002-20261104，再up --no-build --no-deps应用。基线构建首轮误用原始ID为FROM导致403，改本地同ID标签后成功，失败未影响服务。

14:59:45北京时间新应用c4783450…启动，镜像84c1b5fd…；healthy、入口/登录200、启动ERROR0、两个目标SHA匹配。原环境参数、挂载/端口完全一致，5000/SearXNG/relay ID及启动不变；部署前8项研究均已结束。原env/Compose/运行资料私有备份在ldr-experiments/subtask-handoff-deploy-20261104，详见[记录](subtask-handoff-20261104.md)/[部署JSON](subtask-handoff-deploy-5002-20261104.json)。

未改核查/共享写作/数据库结构/历史报告，不调用新模型或创建研究；此前422回归/两篇固定材料试跑边界保持，不作为完整质量验收。未提交推送合入main，fetch仍认证失败。下一步观察新版真实任务，再单独处理核查问题。

## 子任务交付第一版（2026-11-04，已实现验证，当时未部署）

按用户确认先改子任务，核查留待下一步。新增subtask_handoff.py及Agent接入：研究梳理＋原文选择；程序按原来源定位/复制、短摘要完整保留、长文上下文/出处/范围/预算状态明确；主任务区分组织建议与事实材料。新增子任务提示/AI及Tool消息/交付trace，沿用原脱敏权限。核查、共享generation、原trace模块及开关未变，无题目专用规则。

19新增测试、完整422回归通过；断网一次性镜像实际安装/导入通过，未改核查等模块SHA。默认模型两篇固定摘要＋模拟搜索的两个并发子任务和接收成文验证23.157秒：两份结构化作业、4卡原文/SHA/区间完全对应；有限阅读正确区分分子作用与缺失后果，非新检索/全链质量验收，接收输出未遵循中文要求。辅助脚本TypeError、早期迭代限制/无据接收输出及JSON前说明触发回退等失败保留；已修复包装JSON解析并回放原输出。

详见[实现与验证](subtask-handoff-20261104.md)；私有产物`/data/ningh/nh/ldr-experiments/subtask-handoff-20261104/`。原服务/报告/用户库不改，无部署重启、提交推送；fetch仍认证失败。下一步更多题目验证后部署，再单独处理核查；不能将材料保全视为语义核查已修复。

## LRRC4机制方向反转诊断（2026-11-04，未部署修复）

沿ea2efee8任务完整trace定位：原摘要正确，最早可见错误在research_subtopic汇总，主草稿/Writer沿用；Writer和写后核对均收到完整原摘要，核对仍把“LRRC4缺失”的保护机制判supported。排除该段截断与编号错配；模型把主体状态与机制关联判断错，非状态解析漏处理。

5次当前默认模型隔离请求：原8条批次、通用关系提醒、加入独立源发现三种原批次均漏检；只读来源可正确提取，6个中英文正反对照仍误报1个正确中文双句。未把候选提示当修复或上线，未修改应用/配置/原报告或重启，未重新检索或读取用户数据库。详细边界、代码入口与建议见[诊断](lrrc4-direction-diagnosis-20261104.md)；私有请求/回复和仅修正一段的勘误副本在`/data/ningh/nh/ldr-experiments/lrrc4-direction-review-20261104/`。下一步先验证完整关系保全/句间主语切换及跨主题正反例，再决定后端实现；保留原QC关闭及局部修订保护。Git fetch仍认证失败，未提交推送。

## 新增文献真实性要求、调整核心优先级（2026-11-04，仅记录需求）

用户明确新增：“文献真实性：返回的必须是真实存在的正式文献（有 DOI / 可打开链接）”。记录为LDR-08，要求正式出版身份与DOI/链接所指文献一致，不把预印本当正式文献；网络失败或身份不明不能算核实通过。已在roadmap写明正反例和最终参考文献/导出的验收边界，尚未实现或部署，已有身份去重与旧核验模块不作完成证明。

用户调整顺序：当前优先核心优化（真实性、检索/证据覆盖、引用语义和选文条件），登录持久性及开发工程完善保留到后续；此前先修登录的建议不再执行。核心改动仍需必要测试，继续先5002验证再合入main。本轮仅更新待办、当前状态、总索引与本记录，没有修改应用/配置/历史结果，没有模型调用、部署或重启，也未提交推送合并。

## 5002既有研究过程导出（2026-11-04，仅只读取证）

按用户要求导出任务ea2efee8-1e35-46c2-8039-02536a5faf6e的14个trace单元、76条快照；逐条字节数/SHA256一致，无容量省略。包含Agent消息/11条工具返回、72来源、实际Writer输入/草稿、7组核对、49条最终展示来源，并用运行日志补充检索和保存过程。原始gzip、可读文件、manifest和ZIP均在仓库外私有目录`/data/ningh/nh/ldr-experiments/poi-process-20261104-ea2efee8/`，不复制用户原始材料到开发文档。

未调用模型、重跑研究、解密用户库、修改应用/配置/报告或重启。子专题逐次内部模型输入输出和原始HTTP/XML未完整保存；publication_output未与数据库逐字回读比较，无修订不代表独立语义验收。复查两worktree状态，fetch仍因HTTPS认证失败；未提交推送。下一步按用户需要查看导出，不自动修改研究流程。

## 文档集中整理（2026-11-04，仅文档）

用户要求完整整理开发及记录文档。本轮盘点两工作区，合入main独有的5000部署说明/JSON到开发文档集合；补齐两个旧开发流水中独有事件的追溯入口。新增总索引、当前状态、待办、逐文件目录与整理核查记录；更新当前流程、源码布局、部署和5002说明，原文逐字节留档。日期记录标注适用阶段，JSON/截图原样保留。主工作区和工作区外资料索引增加导航，不改变main功能状态。

验证范围为目录覆盖、当前说明的本地链接、原始快照与JSON/截图完整性、变更仅文档、运行容器未变化；结果和历史缺失链接明细见[整理核查](documentation-audit-20261104.md)。本轮没有新增模型调用、研究、账号、构建、部署或重启，未提交推送合并。此前本会话403离线回归与87文件核对仍适用，文档变更不重复运行应用回归。

下一步：依据具体需求选择待办，先完成5002的相应开发与验证。当前默认模型、三源、500来源、原生事实检查开、保存前QC关、自动全文默认关和私有trace开保持。

## 本会话基线核对（2026-11-04）

main与UI分支HEAD均e9be103，远程main已通过连接器只读核对相同；Git CLI认证仍缺失。5000为main-20261028，5002为accounts-5002-20261102，均healthy/登录200。5002共87补丁及独立模块与工作区计入安装转换后相符，403离线回归和模型选择脚本通过。详见[接续概览](project-overview-20261104.md)。

## 最近功能事件

| 日期 | 事件 | 状态与记录 |
| --- | --- | --- |
| 2026-11-02 | 普通用户/管理员/root、审批及简化工作台 | 已部署5002，未合入main；[账号角色](account-roles-5002-20261102.md) |
| 2026-10-30 | 闲置掉登录 | 仅诊断，未修复；[登录诊断](auth-session-diagnosis-20261030.md) |
| 2026-10-30 | 中文界面、主题和侧栏 | 已部署5002，未合入main；[中文](ui-chinese-20261030.md)、[主题](themes-5002-20261030.json)、[侧栏](sidebar-5002-20261030.md) |
| 2026-10-28 | 代理身份断连、工作台 | 主要断连已修，工作台已部署5002；[代理](search-connectivity-20261028.md)、[工作台](ui-workspace-20261028.md) |
| 2026-10-28 | 后端main同步5000 | 已执行；[5000部署](deploy-main-5000-20261028.md) |
| 2026-10-27 | 写后核对、编排修复和身份桥 | 工程已实现，仍有语义限制；[证据流程](evidence-flow-20261027.md)、[模型对照](review-repairs-model-comparison-20261027.md) |

## 完整历史与旧基线

- [UI工作区原始开发流水](development-progress-history-20261104.md)：含工作台、中文、角色以及旧M阶段/旧下一步，均按当时时点理解。
- [main工作区原始开发流水](development-progress-main-history-20261104.md)：额外保留5000生产部署与面向使用者整理README事件，不能用UI副本替代。
- [M0基础记录](verification-foundation-20261012.md)、[旧严格计划](ldr-verification-engineering-plan.md)：历史依据，不是当前开发路线。

以后每次会话记录修改内容、验证范围、限制、提交/部署（如有）和下一步；不写入密钥、原始用户研究材料或私有全文缓存。详细过程使用单独日期记录，避免本文件再次增长成混合历史。

### 2026-11-15 — selected integrity fixes prepared for main; broader goal paused

User authorized pushing the recommended bounded fixes to remote main. The patch
was assembled in an isolated worktree from origin/main 5a1e2a04; the original dirty
workspace and immutable evaluation/independent-review artifacts were preserved.
No evaluation attempt, model call, deployment, service restart or monitoring was
started. The hallucination-reduction goal remains paused and unmet.

Selected changes:
- PubMed primary abstracts are reconstructed once, preserving nested text/tails,
  section order and labels, without merging OtherAbstract translations.
- Explicit Interpretation/解读 annotations retain their original draft paragraphs;
  trace metadata identifies annotations with scientific status unknown.
- Quarto/RIS export supplied bibliography fields and literal notes without
  inventing publication year, language, publisher or access date. The structural
  Markdown parser is an export dependency only; report claim extraction,
  publication schema and runtime review remain unchanged. The overlay manifest
  gains only the RIS exporter installation entry.
- PubMed preserves structured Boolean/field/quoted/date syntax through optimizer
  and simplification paths; topic volume no longer adds an implicit date window.
  Operator days_limit remains in the transport. No lexical fallback, provider
  ranking change, search proxy, source classifier or production setting is added.

Validation: 25 focused tests passed in an offline disposable container using the
existing astro-dra:main-20261106 image, with the isolated manifest overlays and
research_verify package installed. This includes actual Quarto/RIS exporter tests
and frozen-transport AST execution of the actual PubMed adapter methods. No model
or external source endpoint was called. The updated legacy subtask-scope suite
could not collect on the original main baseline because publication.py imports
paper_identity missing from evidence.py; that existing issue remains unresolved.
Full-suite success, scientific citation correctness, full Quarto rendering and
report-level hallucination reduction are not claimed. Experimental automatic
repair, source classification/schema changes, runtime configuration, the known
PMC URL extraction defect, evaluation bundles and temporary scripts are excluded.

Next work, upon explicit authorization: address the existing baseline import
inconsistency separately and obtain independent whole-report outcome evidence
before selecting any experimental repair chain for adoption.

### 2026-11-18 — evidence-grounding and fail-closed held-out checkpoint

Prepared an isolated collaboration branch from `origin/main` for the reusable
evidence-grounding contract and held-out review integrity fixes. The code stays
in the owned `local_deep_research/research_verify/` overlay used by the Docker
install path. The checkpoint includes explicit scope metadata, source-indexed
enrichment with conflict preservation, exact evidence locators, frozen manifest
hash checks, and acceptance checks that reject empty, missing, duplicate,
mismatched, or unbound review rows. Distinct assertions may share a case ID.
Zero-assertion reports require complete per-arm case receipts and an explicit
reason. No report text is edited and no production release gate is added.

The private held-out dataset, gold labels, arm key, blinded packets, source
bytes, provider traces, and run artifacts remain outside Git. Focused validation
passed nine tests, import/compile checks, and `git diff --check`. The existing
origin baseline publication import mismatch (`paper_identity` absent from
`evidence.py`) remains outside this narrow port. Human blinded review and any
hallucination-reduction claim remain pending.

### 2026-11-18 — opt-in observable model debug capture

Added `research_verify.debug_capture.capture_chat_completion` on the evidence
checkpoint branch. It can persist complete request payloads, raw response bytes,
parsed response JSON, hashes, usage, finish reason, timing, visible output, and
provider-returned reasoning fields for controlled runs. It does not and cannot
recover hidden model chain-of-thought that the endpoint does not expose. Capture
is opt-in, private-directory only, and unchanged for normal runs.

### 2026-11-20 — branch consolidation and streamlined runtime

Consolidated the GitHub branch histories with the current main integrity commit as an ancestor. Kept the opt-in model capture helper, its focused tests, the held-out review validators, and the deployed search, writer, source metadata, and export paths. Left 504 checkpoint additions in history, including 358 one-off scripts. Removed inactive writer variants for evidence-gap attachments, semantic reranking, source detail material, and retention retries. PubMed shares a successful XML batch across abstract and metadata readers and preserves structured queries.

The selected deployment defaults require an operator-supplied model and endpoint, use an optional search proxy and an effective 500-source limit, enable native fact checking, and keep save-time citation QC off. A local JCR catalog is still required for live metrics.

Validation used the existing base runtime in disposable containers without network access. Overlay/account installation passed. The installed core suite passed 109 tests, the focused source suite passed 163 with one installed-runtime test deselected, and all four PubMed constructor checks passed. Compose defaults, optional SearXNG proxy rendering and Git whitespace checks passed. The broader installed suite returned 561 passes and 90 failures, including legacy citation/audit contracts, old subtask fixtures, and the inventory test's missing container CLI. Live research quality and production deployment were outside this run.

### 2026-11-20 — custom report keyword coverage removed

Deleted the report keyword checker, its configuration and result model, the recheck CLI, and their strategy, build, and metadata hooks. The archived report parsers still recognize saved coverage sections. Literature search queries and article-supplied keyword metadata are outside this feature.

A clean overlay install confirmed both deleted modules are absent. The old config flag has no effect, legacy report parsing still separates the old appendix from claims, and regenerated metadata omits the obsolete private fields. The focused installed suite passed 148 tests. The broader installed suite had 554 passes and 88 existing failures, with zero new failures versus the previous main. Both Compose files and whitespace checks passed. No deployment or saved-data migration was performed.

### 2026-11-23 — remove free-text rules from prompt routing

Audited the active LangGraph, synthesis, PubMed, Europe PMC, and SearXNG paths against the 5006 baseline `05da5b4`. Removed the shared IF regex and the two tool gates that depended on it. The lead and writer offer the existing source-bound JCR tool, and each model decides whether its request needs a lookup. Ranking-only requests can omit the threshold. The adapter reports a missing catalog without creating an empty database.

PubMed and Europe PMC return the zero-hit outcome for the submitted search instead of constructing shortened searches from stopwords and fixed word windows. Removed PubMed's unused historical keyword and date-expansion helpers. The optional PubMed optimizer receives explicit scope-preservation instructions and falls back to the submitted query if its output is unusable. PubMed search syntax protection and explicit settings validation continue to apply.

Validated in disposable containers based on the 5006 image. The focused suite passed 141 tests. The expanded suite passed 159 and failed two subagent handoff cases, both reproduced against `05da5b4`. An offline tool-calling smoke check confirmed equivalent tool exposure for wrapped, paraphrased, and explicit IF requests, a source-bound lookup using the host catalog, and a plain writer completion without accessing JCR. Tool-enabled writer callbacks deliver the completed text in one chunk. The smoke check used scripted model messages.

The code is on the isolated `codex/remove-prompt-rules` worktree. Port 5006 has not been redeployed or rerun. A live IF regression still needs the JCR catalog staged for the service and successful model transport.

### 2026-11-23 — deploy prompt routing and JCR catalog to 5006

At 09:43 CST, switched the `astro-dra-5006` application service to `astro-dra:f5564c3-5006` (image digest `sha256:2c6401eca6c8e6c238800068c64b8dd63d20b4aa882cdccb16cb8eafb836cc7a`). The new image overlays the eight changed runtime files on the previously running image, retains its source-collection hook, and includes the host's read-only JCR catalog. Preflight found root-only staging permissions in the first source reconstruction and the first overlay image. The source reconstruction contained `research_verify.pmc_identity`, which was unreadable by the application user. A clean reconstruction with readable staging permissions later passed the module import and JCR lookup as `ldruser`. The deployed image passed the catalog integrity and tool-call checks as `ldruser`.

Updated only the application image selection in the existing instance environment and recreated that service. The existing data and configuration mounts, original research trace, and model relay and SearXNG container identities were verified after startup. Docker reported healthy and the external login page returned HTTP 200. A live model smoke request returned in 1.6 seconds. A separate live writer test sent a wrapped Chinese IF request and performed a source-bound JCR lookup against the 2025 metrics with the requested strict threshold.

The original 20-paper research job was not resubmitted during deployment. The short model checks do not establish long-context performance or address the prior relay idle timeout.

### 2026-11-23 — reconcile the original h100 worktree with GitHub main

The pre-fix tumor IF run exposed three failures. The stored question contained a hard line break inside the Chinese IF label. The old parser returned no threshold, which disabled the lead and writer JCR tools. Its image also lacked the JCR catalog. The agent reached its iteration limit and drafted from the first 20 source snippets, leaving seven unranked candidates. Source reading and writing then each hit three relay idle closures after 120 seconds without upstream response data. The application stored the draft and marked the job complete. The 5006 rollout above addresses the tool routing and catalog. The long-context relay failure and the number of fully eligible papers remain unverified.

Compared the original worktree and index against GitHub main and the November 20 checkpoint. Among the paths present in main, 63 worktree versions matched main, 40 matched the earlier checkpoint, and this progress log had an unpublished operational entry. Another 506 files matched checkpoint paths removed in the consolidation. The staged IFCheck changes predate the documented JCR migration. The local evaluation material, archived experiments, JCR database, and original index were retained in the source checkout.

### 2026-11-23 — report reliability and runtime simplification

Fixed the six defects from the 5006 engineering review on `codex/fix-research-reliability`. The writer selects the terminal assistant message, sizes its tool budget from the supplied sources, and retains journal receipts if plain synthesis must retry. An incomplete report preserves useful body text, stores a failure reason, and uses the existing failed status and notification path. Earlier subagent scopes cannot register sources after their deadline or a collector reset. The JCR adapter accepts a catalog in the persistent data volume, a configured file, or an explicitly staged image catalog. Advisory IF checks apply the current constraint to the recorded metric.

Quick and detailed reports now share persistence, source storage, terminal status, and notification. Removed the unused PubMed result counter, inactive report renderers and methods, unused calculations, and a redundant serialization pass. The shared path uses the search system already created for the run and retains legacy findings and report-format compatibility where callers still rely on them. Compared with `6978b82`, handwritten production and deployment code has 533 added and 1,100 removed lines. Tests have 184 added and one removed line.

Installed the overlays in network-disabled disposable containers. The full suite returned 563 passes and the same 88 failing test IDs as the base revision. Scoped mypy checks retained the same 57 existing diagnostics. Ruff correctness checks, Python parsing, Compose rendering, and Git whitespace checks passed. A Docker build probe retained the staged JCR catalog while excluding an unrelated SQLite file. Live long-context performance and behavior of external collector implementations remain unverified. These commits are local and the 5006 service still uses its earlier image.

### 2026-11-23 — simplify fragile research pipeline rules

The retrieval path preserves PubMed and Serper query syntax. PubMed ESearch reuses the paced retry transport, including Retry-After for rate limits. Failed relevance batches contribute explicitly unscreened candidates under the existing result cap. The local JCR adapter resolves journal identifiers from PubMed and Europe PMC metadata, using exact journal titles when identifiers are unavailable. Three journal aliases resolved against the read-only deployment catalog.

Removed the extra lead-agent draft over its first 20 collected hits. The normal writer receives the accumulated pool under its existing evidence budget. A failed source selection samples across each batch. Source excerpts can retain acquired appendices and use the retrieval query alongside the user question. The reader accepts short exact evidence, and active review leaves verdicts without located support unresolved. The report deadline stops the detailed path from starting a writer after the budget expires. A request already in flight remains subject to its transport timeout.

Detailed report cleanup now removes exact duplicate headings and recognized bibliography entries. Study headings and ordinary lists are kept. Save-time citations use Markdown spans and stable source identity. The renderer retains code, distinguishes unresolved references, and checks structured error fields instead of treating an answer beginning with Error as a failed run. JSON recovery only removes comments and structural trailing separators. The intentional date-template substitution and embedded bibliography conventions used by legacy publication records were preserved.

Four local implementation commits end at `606f84a`. Handwritten production code changed by 388 additions and 1,531 removals, for a reduction of 1,143 lines. Tests changed by 143 additions and four removals. There are no generated-code changes. Sixty focused tests passed in the installed runtime. The full network-disabled suite had 573 passes and the same 88 failure IDs as `6d76cde`. Scoped mypy passed for nine evidence and retrieval modules. Ruff correctness, Compose rendering with fixture values, and Git whitespace checks passed. The 5006 service remained on `f5564c3-5006` during verification.

### 2026-11-23 — live 5006 run e92ae839 and source-selection recovery

Reviewed the application, SearXNG, model relay, Strata health and the per-run synthesis trace. The task started at 09:46:49 CST. PubMed returned HTTP 429 once, several PDF or HTML requests failed, and two subagents hit their task deadline. These events left the lead agent running. It reached the LangGraph iteration limit at 11:39:57 with 142 sources. The saved source snapshot contains a numeric IF for 34 records. The app logs show 35 numeric JCR tool responses and five unresolved journal lookups.

The old fallback draft call was closed three times, at roughly 120 seconds each with zero upstream bytes. It failed at 11:45:58 and final writing started with an error-placeholder draft. The first of nine serial source-selection batches then had the same three relay timeouts and failed at 11:52:01. The old application took its fallback and started batch two. The app container and the Strata health endpoint were healthy. The available logs establish the relay's idle closure and the retry cascade. They do not establish why the upstream did not emit data within the deadline. At the last check, the task was at 90% and had no saved final report. No running container or task was restarted.

Commit `d096d3e` stops further optional model selection after an invocation error while preserving cancellation and per-batch recovery for malformed responses. In an offline replay of this run's saved 142 candidates with one injected timeout, model selection was attempted once and the nine fallback batches supplied 70 sources in 198,621 characters within the 200,000-character budget. The full suite on this revision returned 574 passes and the same 88 failed test IDs as the baseline. Scoped mypy and Ruff correctness checks passed. Across all fixes since `6d76cde`, handwritten production code is +419/-1,547 lines, tests are +164/-4, and generated code is unchanged. The branch remains local to h100 and the active task is still running the prior image.

### 2026-11-23 — deploy 34dc260 on 5006 and submit the tumor IF rerun

Built and deployed `astro-dra:34dc260-5006` from a clean archive of commit `34dc260c500e0c8ce776331a0f6edfc897553418`, over the previously deployed runtime. The image digest is `sha256:250c48ddb0de4876d75dddce1cd2b11695d52579da996f91c154d08b3bae6f83`. The prior task was terminal before restart. Preserved the 5006 data and configuration mounts and the existing SearXNG container. Changed the private model relay idle budget from 120 to 600 seconds to allow long requests to reach the model response. The prior instance configuration is backed up under `/tmp/astro-dra-5006-rollback.LmyIEF`.

Validated the image and running process, the login page response, model health via the relay, and an authenticated short model completion in 0.87 seconds. The running application account resolved Cell Reports Medicine's JCR record by its electronic ISSN. The old report remains accessible. Submitted a new quick research job, `8917393a-634d-452e-88fc-6f68064c7f51`, at 12:54:46 CST. Compared the application start log to the exact prompt copied from the user's message. The new run started successfully. Its final synthesis and eligibility count have yet to be verified.

### 2026-11-23 — 原文选段方案和匹配规则盘点

用户确认按论文结构保留材料、按字段语义排序、对缺证字段扩大阅读的方向。先写入[原文选段 README](README-evidence-selection.md)，留待后续实现。以 5006 实际安装的 `34dc260` 核对网页取证、writer、原生核查、搜索查询路由、模型索引格式、来源去重和可选路径。用运行容器中的实际函数回放显式约束、PubMed 括号识别、两套模型索引解析和来源身份去重，经合成 trace 确认第 4、10 批位置回退。旧逐引用 QC 配置为关闭。当前主链的词面选段集中在取证、写作组装和核查组装。下一步按 README 的固定原文案例比较证据覆盖和耗时。此轮仅改文档，应用、配置与部署未改。


## 2026-11-23 · README evidence-selection implementation and 5006 replay

Implemented structured task requirements, explicit PubMed/Europe PMC query plans, ordered report outlines, structured source selection with one format retry, article retrieval bound to stable identifiers, retained semantic source passages, focused rereading, per-assertion evidence receipts, task coverage, journal/year JCR reuse, shared eligibility counts, duplicate screening reuse, and partial subtask delivery.

Deployed `astro-dra:evidence-selection-5006` and submitted the exact saved `d4399cbe` prompt. Its plan described the IF requirement in prose but lacked the structured metric. That run, `14e0e10f-0ca1-4636-bdea-e75ef0de4f1d`, was suspended through the research API. The follow-up validates the fixed metric schema, recovers literal spans across copy/paste whitespace, and gives an omitted or malformed metric one narrowly scoped retry.

5006 now runs `astro-dra:evidence-selection-v2-5006`. Exact-prompt replay `6eef6482-7e81-4fb8-8bbe-a9947613cb06` is being monitored. Source snapshot replay preserved nine Xenium mentions from the acquired gastric paper and all four Visium mentions from the acquired melanoma paper in the same writer/reviewer passages. The two Nature Communications source IDs 31 and 59 share the 2025 catalog result of 18.1. The initial source tree and both deployment rollback configs are retained.

The v2 run confirmed that the original query maps to 2020–2026 search dates, 2026 report eligibility, IF ≥ 10, and a target of 20. Europe PMC reused 11 of 12 screening decisions in a repeat query. A production transport replay exposed an XML timeout on the iCCA article while the official PMC HTML returned the same DOI and article text. Added a verified PMC HTML fallback with structural paragraphs and gave fresh screened candidates priority before the result cap. The v2 probe was suspended through the API. V3 is healthy on 5006 and its exact-prompt run `816f9570-ed80-4623-968b-1c80306f9e18` is monitored. In the same isolated test setup, baseline 574 passed / 88 failed and V3 588 passed / 85 failed, with no new failing test IDs.

### 2026-11-24 · Live synthesis follow-up

The exact-prompt research stopped issuing new searches after repeated actions produced no new evidence, then handed 112 collected records and an empty lead draft to synthesis. The trace exposed a task-plan assignment onto the citation facade instead of the delegated writer. Fixed the handoff and staged a checkpoint replay against the same source snapshot and inference service. A local catalog check matched 93 of the 112 source records, of which 73 meet the requested IF threshold.

In the live run, one of six source-selection batches reached the inference queue deadline and preserved 17 unresolved candidates. The original material pack admitted no fresh selection because the earlier article views exhausted the context. A fixed-input replay preserved 35 source records under the same 200,000-character limit, including 10 fresh selections and the primary Xenium evidence from source 98. Additional repairs bound DOI validation to the existing egress policy and a batch timeout, and removed leftover title-delimiter parsing and table-specific wording in the detailed report. The 5006 job and separately launched writer checkpoint are being followed through output.

The live checkpoint's first evidence-gap pass selected all eight targets from source IDs 2–15 because the planning prompt admitted full blocks until it ran out of space. Candidate previews now share the planning budget across all eligible leads. Regression checks verify independent claim states in prose, list, and table formats and allow the last of 100 candidates to be selected for rereading. On the isolated comparison harness, v10 recorded 600 passed and 85 failed, with no new failure IDs against the 574-pass / 88-failure baseline.

Deployed `astro-dra:evidence-selection-v10-5006` at 01:51 CST and verified the app, inference health, and model list. The relay had twice closed the same source-reading request after 600 seconds without upstream bytes, while the backend queue can wait for 30 minutes. Updated the instance-specific relay idle timeout to 2,700 seconds. Suspended the obsolete v3 web job via the application API after preserving its source checkpoint. The six selection receipts and eight reread results from the isolated intermediate replay are reused using the same input digest. The final v10 checkpoint `a278becd-97e5-40b8-a312-29e419d1699d` reflects the latest writer and reviewer, with 40 original source views including the missing gastric paper. The two Compose files can be restored from `/tmp/astro-dra-5006-evidence-v10-rollback-q2iqYQ`.

The v10 checkpoint produced a 17-entry draft. The admission ledger was consistent for the historical gastric and false-platform cases, but the writer did not receive some of the validating quotes, and cumulative source size caused two review groups to be skipped. v12 attaches original admission quotes to source views and budgets every cited source in a review group. A single oversized claim can safely reuse the exact source-scoped writer views. The saved draft replays as seven review groups within the 52,000-character evidence budget and restores 12 omitted exact quotes. The deployed application is `astro-dra:evidence-selection-v12-5006`, with rollback `/tmp/astro-dra-5006-evidence-v12-rollback-6J4GEX`. The shared relay remained online. Integration checks show 603 tests passed / 85 baseline failures (zero new IDs), and final checkpoint `61dbc850-2620-408e-b5ea-be7cab43477c` is monitored through writing and consistency review.

The v10 intermediate replay finished with 17 citations and incomplete review. Three groups hit the old packing failure. The native reviewer and independent repair verifier did correct source 6, whose draft put training and validation datasets into the Xenium cohort column. v12 completed its writer call in approximately 691 seconds with the updated relay and produced 19 ranked records. Source 52 was independently verified after v13 switched joint criteria to separately located original quotes. v13 is healthy on 5006, with rollback `/tmp/astro-dra-5006-evidence-v13-rollback-ya0rL0`. The comparable suite now shows 604 passed / 85 original unchanged failures. The combined report preflight resolves 20 distinct paper DOIs including source 52 at rank 10, pending the v12 native review and final audit.

The v12 synthesis and task-coverage replay completed at 04:20 CST after about 5,884 seconds. All seven native review groups and their 21 units were processed without a material-budget skip. Four source-supported repairs were applied. The raw report contains 19 cited papers and preserves four unresolved review receipts. The separately verified v13 source 52 was added to the audited report at rank 10. The combined audit validates 20 distinct 2026 DOIs, descending 2025 JCR IF from 81.2 to 10.8, and explicit labels for unverified sample counts. The v13 application and its 2,700-second instance relay remained healthy. Final artifacts are in `/tmp/astro-dra-evidence-EBXZpQ/checkpoint/`.

The v14 coverage-only replay finished after 151.5 seconds with six answered checks, one partial grouping check and one unchecked sample-size check. Like source admission, coverage now accepts independently located exact spans, preserving unverified field states. The report independently verifies the count, dates and descending IF, and 12 rows explicitly mark at least one unavailable field. v14 is healthy on 5006. Its application-only rollback directory is `/tmp/astro-dra-5006-evidence-v14-rollback-tRzMXf`.

### 2026-11-24 · 通用任务条件复核

按用户要求先记录方案。静态检查确认了 IF 缺省触发规划重试、篇数控制写作前纳入核查，以及 IF 缺省进入工具写作流程。另记录既有 JCR 元数据影响纳入、排序和补读的边界。在[原文选段 README](README-evidence-selection.md)的「通用文献检索的任务条件解耦」一节列出位置、拟修复方向及跨学科验收场景。本轮更新文档，代码、测试和部署未改。待用户安排后实施与回放。

### 2026-11-24 · README 更新为当前版本问题

应用户要求，[原文选段 README](README-evidence-selection.md)现以 5006 的 v14 为准，仅保留当前版本问题与验证缺口。核对运行镜像和工作树的五个相关模块哈希，并在运行容器中用固定输入复现 IF 规划重试、篇数耦合、写作工具分支和已有 IF 门槛影响纳入。核查现有覆盖回放仍有分组和样本数缺口，尚待 v14 端到端复跑。历史故障及对应修复见前面的进度记录。本轮为文档更新。

### 2026-11-24 · 去掉检索前的独立任务规划调用

主智能体直接读取原问题，按需在正常搜索工具调用中提交有原话依据的纳入条件、提取问题、搜索范围及交付要求。PubMed 的查询改写只整理数据库所需的概念和年份。目标篇数不再触发纳入核查。JCR 查询、门槛与排序依据本次明确条件；带 IF 标记的旧来源在一般任务中不会因该标记影响纳入、补读或排序。

真实模型复现了将门槛和排序引文用省略号拼接导致的结构化 IF 丢失。要求引用一段连续原话，并在模型已声明指标但字段不完整或引文无法定位时，于写作前尝试一次定向核实。归一化成功后，JCR 检查结果和逐篇失败原因进入综合跟踪及 writer。常规任务直接写作。

使用候选镜像 `astro-dra:conditional-task-conditions-check` 验证。开放式教育问题的首个真实模型工具调用省略任务条件。原肿瘤提示词的首个调用识别出 IF ≥10、降序、目标 20 篇及独立搜索和报告年份。使用相同候选镜像对本任务 112 条存档来源查本地 JCR，73 条达到 IF 门槛，20 条有指标但低于门槛，19 条未查到。该计数只衡量 IF。固定模型回归验证了写作前实际查期刊、达到门槛的条目不足目标时根据实数输出，以及无篇数的纳入核查。离线全量测试为 608 通过、85 个既有失败，无新增失败用例 ID。Ruff、Python 编译、Git 空白检查及四个核心模块的定向 mypy 通过。generation.py 仍有四个可在基线复现的类型注解错误。

代码、回归测试和候选镜像已准备。5006 当前运行 v14，本轮验证范围为真实模型首个检索调用和固定输入回放。完整实时检索到报告生成仍待验证。

### 2026-11-24 · 篇数作为普通交付要求

从上一候选版移除 `goal` 和专用 `eligible_count` 字段、资格名单的篇数截断及正文计数占位符。核查入口仍由实际纳入条件决定，删除 `assess_eligibility()` 内重复的提前返回。确认与待核名单保留全部判定，篇数通过普通交付要求和用户原话交给 writer。显式报告设置中的篇数仍可传给 writer，字段取证使用既有准备预算。用交付 1 篇的设置确认字段取证仍处理默认的 6 条候选。

候选镜像 `astro-dra:delivery-count-only-check` 用三条指定提示跑固定来源回归，3 项全部通过。真实模型试验也复核了首轮工具参数和固定来源报告。只要随机对照试验触发纳入核查并列出 6 篇。给我 5 篇代表性论文跳过专项核查并列出 5 篇。给我 5 篇随机对照试验触发核查，6 个已确认 ID 均传给 writer，报告列出 5 篇。两次随机对照试验报告都在排除说明里提到观察性研究，合格名单里没有该研究。初次真实模型漏交了并存的设计与篇数，后续加固搜索工具参数说明及通用写作交付说明。此验证使用固定来源，未跑线上端到端数据库检索。

离线全量测试 611 项通过，85 个失败用例 ID 与上一候选版本完全一致。定向 Ruff、mypy、编译和空白检查通过。改动已同步到 h100 工作树。5006 在线版本仍为 v14。

### 2026-11-24 · 跨题目泛化审查

对照 5006 v14 的已安装代码和 h100 候选工作树，沿检索、纳入、取证、写作、核查及发布入口审查。固定输入复现：年份和研究设计引用同一段用户原话时，观察性来源可被仅按年份确认为合格；候选工作树两次工具调用先后提交同类纳入条件，仅保留第一次的列表；仅有权威页面 URL 的来源跳过定向补读；布尔检索编译仅保留前 8 个概念组、每组前 8 个词；条件匹配器对德法语或列表形态的英语返回未知。在 v14 的 writer 来源块上复现了仅存在于结构化字段的敏感度、特异度和随访时间未传入，平台与样本量可见。线上默认检索工具说明与通用 writer 提示包含具体空间组学示例，属于提示偏向，未测量跨任务质量差值。现有 18 题冻结来源的对照可验证写作，仍需覆盖从新检索到报告的异题评测。本次只做审查，未改服务代码或部署。

### 2026-11-24 · JCR 按需调用与交付篇数合并验证

删除任务计划里的专用 IF 字段、合成前的 IF 补问和全量查询，以及按 IF 切换 writer 的工具循环。研究智能体在现有 `search_journal` 调用里声明展示、筛选、排序或两者。参数校验随同工具调用执行；筛选要求显式门槛和操作符，排序要求显式方向。实际查证回执随来源交给普通 writer。缓存按期刊身份和指标年份保存值，门槛按本次工具用途重新计算。旧回执不参与另一任务的纳入、补读或排序。

在候选容器里回放 README 的示例。开放式教育问题的真实模型回放有零次期刊查询。展示型验证在固定候选集的检索后回放中只查 [1]，没有设置门槛。用明确的严格大于 10 的真实模型测试，工具收到大于比较符和降序，18.1 达标，10.0 与 7.9 均不达标。指定年份缺失保留 `metric_year_unavailable` 并交给 writer。本地实际 JCR 表同一期刊两次查询只读库一次，均得到 2025 年的 18.1，第二次严格比较等值不达标。三条篇数与研究设计提示的回归继续通过，公立学校与随访示例也确认了独立纳入及按字段补读。

原肿瘤提示词的三篇固定来源回放取得 18.1、10.0、7.9 的回执并输出两篇、说明少 18 篇。真实模型仍可能把长提示词的筛选和排序当作展示调用，由 writer 根据原话与回执比较。较早的并列相关候选回放也出现展示一篇但查询三篇的现象。加固工具用途后，检索后展示回放查询一篇。测试范围为固定数据及工具回放，完整线上检索尚未复跑。

离线全量 613 项通过、85 个失败用例 ID 与去 `goal` 候选版一致。定向 Ruff、mypy、编译及空白检查通过。相对上一候选版，手写生产代码新增 145 行、删除 278 行，净减 133 行；测试新增 123 行、删除 140 行。代码同步到 h100 工作树，候选镜像已构建。5006 在线镜像仍为 `astro-dra:evidence-selection-v14-5006`。

### 2026-11-24 · 多条件纳入与跨主题元数据交接

纳入核查分别检查已登记的条件，即便它们引用用户同一句话。多次检索可以补充纳入条件、待回答问题和交付要求，同一条目重复提交仅保留一份。来源中的额外结构化数据以原字段名和来源编号进入 writer 材料、子任务来源快照及回放；新扩展字段限可序列化的普通数据、最多 8 层及每个值 4096 个 JSON 字符，排除内部状态和凭据类字段。删除 PubMed、Europe PMC 默认说明的 Visium 和固定年份示例，以及 writer 公共提示里的具名单细胞平台示例。

在独立镜像中验证，三个新增回归在改前均失败，改后全部通过。相同命令和隔离环境下，全套项目补丁测试从 613 通过、85 失败变为 616 通过、85 失败，失败 ID 集合一致。另从安装后的候选包串联检索条件、资格核查和来源快照到 writer 的材料组装，复核部署默认提示。候选镜像为 `astro-dra:cross-topic-generalization-mczhjv`，日志在 `/tmp/astro-general-validation.mczhJV/`。5006 仍运行 v14，本轮未进行新联网检索或生产部署。

### 2026-11-24 · 旧 IF 标记隔离与顺序验收

将 JCR 缓存从单个来源收集器移到进程内的数据库版本，共用期刊身份和指标年份对应的值。工具门槛比较按本次调用计算，工具回执仅写入当前任务状态。旧来源即使仅保存了扁平的 `passes_threshold`，进入 writer 前也会清理旧门槛及关联指标字段。定向补读与 writer 已读材料优先级不依据该字段。确认名单跨写作批次沿用原候选顺序，只有收到明确 IF 排序方向才排序，并将保序要求交给 writer。合并时保留并行工作对任务要求合并及纳入条件核查的改动。

用 PubMed 的 INTER-ACT 随机对照试验（PMID 40466885）及本地实际 JCR 库验收。该刊 2025 年 IF 为 7.9。三个独立收集器依次得到排除、确认纳入并进入随机分组定向补读、确认纳入。三轮实际查库次数依次为 1、0、0。补读以固定 PubMed 摘要片段回放。材料预算测试比较了带旧扁平标记与基线的选材，来源、原文和优先级一致。多批写作中，仅设 IF ≥7 保留 7.9、18.1、10.0 的原顺序，附加 IF 降序要求后得到 18.1、10.0、7.9。另验证本地 JCR 库新增指标年份后 latest 缓存会刷新。

合并工作树构建的 `astro-dra:if-scope-isolation-check` 全量 619 项通过、85 个既有失败，失败用例 ID 与 JCR 按需候选版一致。定向 Ruff、mypy、编译与空白检查通过。5006 在线仍为 v14。

### 2026-11-24 · 通用任务覆盖核查与按需补查

`task_coverage()` 逐条定位报告引文，保留匹配、不匹配、重复匹配及可确定的来源范围。第二步仅以已定位片段为回答证据，按问题需要的范围判断是否采信模型原判。逐来源覆盖按范围和可定位的出处核对；一段明确适用于多个来源的原文可支撑整个范围。

对未回答、部分回答、明确缺证及待核问题，将问题、涉及来源、当前报告、已定位片段和先前查阅记录提供给模型。沿用 article/web 补查能力，模型可选择工具或停止。每份报告至多补查一轮；拿到新证据时只提出局部补全，并复用独立修订核查。报告依据来源证据区分现有材料未核实与原文明确未报告。没有新证据或修订未获支持时，保留原报告和缺口。

使用 v14 的存档模型输出和 20 篇报告复测。混合引文项保留两个精确匹配，各自记录位置，另一条单列不匹配。真实模型在整份存档重放中判为部分覆盖；最终候选镜像的单题重放确认范围为 20 篇，只确认来源 20 被有效回答，仍为部分覆盖。跨问题回归覆盖教育材料、档案政策、标准和技术文档，验证完整、多来源部分覆盖、拒绝虚假全覆盖，以及文章补读、网页补查和停止补查。重现了有精确原文支持的明确未报告，以及新材料仍不能支持该断言的情况。

候选镜像为 `astro-dra:task-coverage-check`。离线全量 626 项通过、85 个既有失败，失败用例 ID 与上一个候选版本一致。定向 Ruff、mypy、Python 编译与空白检查通过。代码已同步 h100 工作树；5006 当前仍运行 v14，验证范围为存档重放和隔离回归。

### 2026-11-24 · 核查范围由模型按任务判断

将用户原话从 LangGraph 传入报告覆盖核查。模型结合原话、报告和定位证据选择核查范围，可合并相关问题。任务笔记提供参考。去掉按来源编号集合决定核查是否完整的分支。程序保留每条引文的位置和状态，对模型引用的片段编号及来源编号核对出处。模型说明实际核查的范围及未决问题，交给已有原文和网页补查。模型可在报告格式允许、正文未交代缺口时加简短的核查范围说明。

候选镜像 `astro-dra:semantic-coverage-check` 用原始提问和 v14 存档重新核查样本数问题。两条报告引文精确匹配，一条未匹配。模型判为部分覆盖，仅指出第 1 篇与第 20 篇报告片段中的部分样本信息，并保留其余缺口。隔离回归验证了同样的来源编号可以对应不同的覆盖结论、多个问题可合并核查，以及自主补查或说明范围。全量 628 项通过、85 个既有失败，失败用例 ID 集合与上一候选版一致。定向 Ruff、mypy、编译及空白检查通过。改动已同步 h100 工作树和 README，5006 仍运行 v14。验证使用存档回放及固定数据，未触发从检索开始的整题新跑。

### 2026-11-24 · 覆盖核查修正与跨题端到端实测

修正三处交接。补证修订含多个引用时，确认器读取新证据以及原句、替换句涉及的来源，材料无法装入则保留待核。即使任务计划没有子问题，也把用户原话送入覆盖核查。核查器产生的范围说明随核查记录保存，未经确认的说明不会写入成稿。覆盖核查与其他审阅步骤共享调用预算。候选镜像为 `astro-dra:coverage-e2e-final-kyynzo`。定向回归 5 项通过，全量 628 项通过、85 项失败，与修改前基线的失败用例集合一致。5006 仍运行 v14。

取六条原始提示词中的第 6 条 Xenium 和第 2 条 RNA 质检，按此顺序用隔离容器、实际检索和线上同款模型测试。第 6 条从检索到生成用时 27 分 20 秒，取回 14 条来源。测试设置的最大输出 4096 tokens 截断了初稿与覆盖核查 JSON，原始报告标为合成未完成。复用这轮归档的 14 条写作输入，将输出上限调至 16384，重跑撰写、核查与报告输出，用时约 25 分 22 秒。重写正常结束，正文引用对应 14 条参考来源。覆盖核查给出 1 项已回答、3 项部分覆盖、2 项证据缺口。原文一致性复核仍有 4 项未决。该补跑验证下游恢复能力，未从头重复检索。

第 2 条 RNA 质检使用 16384 tokens 上限，从检索到成稿用时 60 分 08 秒。取回 9 条来源，成稿引用 5 条，程序正常完成。报告给出了有条件的继续测序建议；覆盖核查把当前样本的决策判为部分回答，把杂峰身份及污染阈值判为证据缺口。补查决策返回空请求。原文一致性复核有 3 项未决。首句保留“通常可以继续测序”，同时正文承认样本放行条件缺乏直接验证。一次事实核查达到 16384 tokens 上限并触发重试。两题均未使用按主题定制的验收关键词。

RNA 成稿还复现了独立的引用范围问题。初稿证据范围说明指向原编号 [1]–[3]；这三条来源在发表版依次改为 [1]、[4]、[5]。成稿只重排区间端点，显示 [1]–[5]，多指向两条材料。逐个链接与文末条目都匹配，单查链接无法检出集合变化。回归应比较重排前后引用指向的来源集合。该问题保留为本次实测发现。

### 2026-11-24 · 更新候选版开放问题清单

重写 [证据选择 README](README-evidence-selection.md)，移除已在候选版修复的待办。对照两题的成稿、检索与核查记录，整理引用重编号、结论力度、检索相关性、目录取证、核查范围和输出截断六项问题，各自附原因、通用策略和验收办法。保留原肿瘤题的端到端验收缺口。已核对文档中的相对链接和运行版本。本次仅更新文档。

按两题实测的用户影响重新排列 README 的六项问题，将过强建议和引用集合变化列在最前，其后为输出截断、检索缺少直接证据、目录读取受限、核查范围扩大。

### 2026-11-24 · 引用区间重编号与截断恢复

在候选镜像 `astro-dra:citation-range-recovery` 中修正旧清单第 2、3 项。新报告按来源身份展开 `[1]–[3]` 这类两端带方括号的引用区间，保存格式为 2.3。旧 2.2 仍用原规则校验，Quarto 按成稿中已有的引用导出。用 RNA 题的原始发布输入复现，原三篇在修复后显示为 1、4、5。

writer 收到长度终止时最多续写两次，续写必须复现前段末尾才能拼接，无法确认则保留已有正文和未完成状态。真实模型在原 4,096 token 配置下对 Xenium 存档续写一次并以 stop 结束，可见正文从 2,577 增至 3,540 字符，原前缀完整。事实核查收到长度终止时分拆未完成的论断组，已完成结果保留。单条再截断或共享预算耗尽时记录未决。覆盖定位截断时改传段落编号，范围核查截断时拆分问题。固定回归覆盖流式拼接、旧版兼容、截断回执、引用身份与共享预算。全量 641 项通过，85 项失败，用例 ID 与上一候选完全一致。测试与回放脚本在 h100 的 `/tmp/dra-citation-recovery.eSrc4c/`。未重新从检索开始运行两题，线上 5006 仍为 v14。

核实了 RNA 首段的来源及保存路径。存档的 0024 写作请求要求优先回答决策，0025 初稿给出条件性“通常可以继续测序”。0028 的核查包含首段，0029 和 0031 都在长度上限停止，0032 将这组记为无有效核查结果。0066 把样本决策判为部分回答，0068 补查请求为空，0069 的正文哈希与 0025 相同。本次隔离运行使用普通 synthesis trace，writer 的 raw_content 等于可见正文；未发现本次请求的独立原始响应采集回执。问题 1 继续保留。
