# 内置示例题库

2026-10-30最新续批：六方向各20题，共120题；本批新增66道知识题在expanded_20261030_v4.jsonl。补充Java基础、内容与渠道、品牌与协作、数据与增长、项目与风险、课堂管理、教师成长及英语求职动机/问题解决主题，全部显式登记追问路由。新来源original-domain-expansion-v4为self_authored/unreviewed，结构校验不代表专家审校。成套快照docs/releases/2026-10-30-bank-v4为120/126题，6道候选仍隔离；配套hash索引不能充当真实语义Embedding索引。以下计数为历史批次。

2026-10-30最新：运行54题，新增市场营销、运营管理、教育教学和英语面试各6题。新题为项目自编情境，来源unreviewed，不声称专家审校或英语等级测评。成套快照docs/releases/2026-10-30-multidomain-v3为54/60题（另6候选未激活）。旧索引和旧会话仍有资产保护。

2026-10-29当前版本：30题（Java17/Python13）。新增12道自编知识题分别在java_fundamentals_v2.jsonl与python_fundamentals_v2.jsonl；6道既有候选仍隔离。新题参考官方资料并登记来源与逐题追问路径；旧题中的预设用户经历问法已中性化。以下18题描述属于历史批次。

成套快照及匹配的离线hash索引见docs/releases/2026-10-29-runtime-v2/：baseline=当前30题，candidate=36题。旧索引未覆盖，配置真实Embedding的服务须重建同题库/同模型规格索引，不能将hash索引视作智谱语义索引。重启后新建面试加载新资产；进行中旧场次保留版本保护，需使用旧成套配置完成或取消。

当前Java后端11题，Python后端7题；Python包括6道知识题和1道Python编码题。
Python主题为语言基础、异步与并发、Web与数据，编码题使用明确的stdin/stdout和6个公开用例。
该题库是项目自编的教学演示材料，不是正式招聘测评或独立评测基准；未进行专家盲审。

Python异步题按项目Python 3.12运行环境讨论协作取消与阻塞IO，不将取消外层协程当作终止线程。
编码题与Java岗位共用“两数之和”任务定义，但具有独立题目ID，检索仍按岗位硬过滤。
添加岗位时须同时提供skill_tree/<position>.yaml与question_bank/<position>.jsonl，主题必须对应技能树根节点。
题目ID必须全局唯一；至少有一道合法非编码题的岗位才出现在选择列表中。

题库增减会改变全局资产摘要；必须重建匹配的索引并重启服务、新建面试。
保留旧索引和已有业务记录，但不能继续使用旧资产版本的进行中会话。

2026-10-26补充：source_registry.json登记来源声明，当前Java/Python旧题均保留unreviewed（参考资料尚未核对），不把结构通过当作专家审题。新建6道参考官方资料的自编候选题位于../question_candidates/，不在本目录，因此不会被QuestionBank.load自动加载。当前18题及既有索引保持不变。

从项目根目录运行只读审校：

```powershell
.\backend\.venv\Scripts\python.exe evals/audit_question_bank.py --candidates data/question_candidates
```

该工具不读取.env，不调用供应商、不修改题库或索引，退出0只表示严格结构/来源登记检查通过；警告保留尚未核对的来源。题库覆盖页/coverage读取当前运行快照，统计题目数量和空难度格；它不读取候选稿或评分锚点。候选内容及发布要求见[维护说明](../../docs/题库审校与发布说明.md)。
