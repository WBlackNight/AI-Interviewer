# 开发日志：智谱Embedding-3与混合检索联调

日期：2026-10-22（Asia/Shanghai）。接续[沙箱日志](开发日志-2026-10-22-P3沙箱.md)，按技术步骤2.4完成真实Embedding供应商接入。用户本轮提供智谱服务端密钥；它仅保存在忽略提交的`backend/.env`中，本文不记录凭据。

## 交付

- 新增ZhipuEmbedder及配置工厂：官方Embedding-3，1024维，L2归一化、余弦排序；hash仍是离线词法基线。两者使用相同过滤、题干输入和RRF参数。
- 仅允许`https://open.bigmodel.cn/api/paas/v4`，以Bearer认证；不跟随重定向，不读取系统代理，不自动重试。每批最多8条，单条最多3000字符，默认HTTP超时15秒；读取分块检查时间与4MiB体积限制。HTTP读超时是网络操作级限制，分块时间检查不等于独立进程强制终止。
- 输入先基本PII脱敏。严格验证模型、向量维度、返回数量、唯一连续index、非零有限数值；按index恢复顺序。失败使用固定类别，不输出供应商原始正文。
- 独立索引`data/retrieval/zhipu-embedding-3-1024.json`，保留既有hash索引；身份包含题库、provider/model/revision/dimensions及校验摘要。启动只读索引，不自动发送文档；相同索引重复构建无外部调用。
- 建索引、检索评测改为消费配置的Embedder。新增`evals/embedding_ping.py`，只输出规格、通过状态和用量，不打印文本/向量/密钥。
- HTTP/WS冒烟新增显式`--embedding-provider zhipu`，默认继续强制hash；合并重启前后检索计数，避免重启清零掩盖早期回退。
- 诊断增加semantic_model和embedding_usage。记录已知token和未知次数，金额不推算；计数仅进程内累积，Embedding尚无持久化的会话预算，不纳入LLM账本。
- 本机.env已显式配置智谱混合检索；仓库默认仍BM25，CI不需要密钥。现有后端重启后读取配置，切换检索版本需新建面试或恢复旧配置。

协议依据：[智谱Embedding-3官方文档](https://docs.bigmodel.cn/cn/guide/models/embedding/embedding-3)。本文限制是客户端保守工程限制，不将字符数当成供应商token上限。

## 验证

| 检查 | 实际结果 |
|---|---|
| 专项测试 | 新增32项；分批顺序/脱敏、HTTP错误/不重试、错误模型/数量/索引/维度/零/NaN、非法响应、超时/体积、端点、配置工厂与回退 |
| 全量回归 | 382项通过，2条既有第三方弃用提示；见验证摘要 |
| 真实连通 | 1条合成查询返回1024维向量，归一化通过；1次请求、9 tokens |
| 真实题库构建 | 11题；2次请求、394 tokens；成功生成独立索引 |
| 幂等复用 | 再次构建返回unchanged；0次调用、0 tokens，索引ID相同 |
| 真实检索对照 | 固定10条合成查询，vector/hybrid各自编码；20次请求、330 tokens、未知用量0，零回退 |
| 智谱面试冒烟 | 合成PDF、4主问题/4次回答、overall=9.3；断线/重复消息/进程重启通过；4次请求、24 tokens、零回退 |
| 离线回归冒烟 | 相同PDF与重启流程通过，hash模式零网络调用、零回退 |
| 本轮外部用量 | 成功请求合计27次，供应商返回757 tokens；非账单金额。首次受限网络探针失败记录1次未知用量，未当作免费 |
| 前端/数据库 | 前端未修改；冒烟使用临时数据库，未重启用户已有实例、未改写业务数据 |

最初非提权pytest受临时目录权限限制并挂起；定位本次两个Python进程后已结束，在获准环境重新执行并通过。首次受限网络探针失败，获准访问官方端点后真实调用成功。失败记录未用于伪造通过结果。

索引ID：`7810a1484eb4c7b3a03f3471e30a9ff0d4277b3f7b1c24665b44b1d831a8bdd5`。
题库摘要：`86dd7d55fbf5cc04ab8d58368c9004003ccc7b74bcff899f5c7ea8dcae2a5f34`。
查询摘要：`99a3fdc52f3b0e2f41d509a4b3610759849a7b0942bd4834b446d4dd77dcbce2`。

### 三策略smoke结果

| 策略 | Recall@3 | nDCG@3 | MRR@3 | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|
| BM25 | 0.95 | 0.991732 | 1.00 | 0.33 | 0.59 |
| 智谱向量 | 1.00 | 0.994853 | 1.00 | 650.04 | 6111.96 |
| RRF混合 | 1.00 | 1.000000 | 1.00 | 620.76 | 817.98 |

同一11题库、相同过滤、k=3、candidate_k=20、RRF k=60，标注未更改。向量与混合分别请求，延迟包含连接和远程API；10条顺序查询的分位数受网络影响，不能解释为融合算法更快或容量证据。此集为开发者标注的冒烟集，不支持独立质量、显著性或真实面试效果结论。历史哈希对照见[离线评测](logs/2026-10-21/retrieval-eval.json)。

原始排名与用量：[zhipu-retrieval-eval.json](logs/2026-10-22/zhipu-retrieval-eval.json)。验证摘要：[zhipu-verification.json](logs/2026-10-22/zhipu-verification.json)。本轮日志只记录合成数据验证，不包含用户真实简历。

## 复现与后续

从项目根目录运行，后端.env需保留自己的密钥配置：

```powershell
.\backend\.venv\Scripts\python.exe evals/embedding_ping.py
.\backend\.venv\Scripts\python.exe evals/build_question_index.py
.\backend\.venv\Scripts\python.exe evals/retrieval_eval.py --output docs/logs/retrieval-zhipu-local.json
.\backend\.venv\Scripts\python.exe evals/smoke_e2e.py --start-server --restart --pdf --retrieval hybrid --embedding-provider zhipu --dimensions 1024 --index-path data/retrieval/zhipu-embedding-3-1024.json
```

下一阶段按技术文档推进P2真实LLM四组件联调和P4独立标注评测；Embedding密钥尚未用于LLM评分/规划，也没有据此声称四组件可用。P3真实沙箱部署仍缺Docker/Judge0，独立保留为未验收。规模扩大前补Embedding全局准入、持续用量/预算管理、独立评测集和并发实测；当前仅为小型题库原型接入。
