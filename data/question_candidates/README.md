# 自编候选题，未激活

2026-10-28续：已配套data/skill_tree_candidates的题号路由与24题候选包，并完成三个离线HTTP/WS场次。新增18条绑定题目版本的作者正反示例；规则评分仍有4例多判、2例漏判，本批不激活、不修改题干或锚点来追逐示例分数。见[最新日志](../../docs/开发日志-2026-10-28-题库候选与发布链路.md)。下文为2026-10-26候选来源记录。

日期：2026-10-26（北京时间）。当前6道知识题（Java4、Python2），只用于内容审校，不在question_bank目录中，不参与练习或现行索引。

| 题号 | 根主题与难度 | 参考登记 |
|---|---|---|
| jv-spring-di-basic-002 | Spring / easy | original-spring-di-20261026 |
| jv-spring-cycle-002 | Spring / hard | 同上 |
| jv-redis-persist-basic-002 | Redis / easy | original-redis-persistence-20261026 |
| jv-redis-fsync-002 | Redis / hard | 同上 |
| py-copy-cycle-002 | Python基础 / hard | original-python-copy-20261026 |
| py-coroutine-start-002 | 异步与并发 / easy | original-python-asyncio-20261026 |

题干和评分要点为项目自编改写，未复制官方代码例子。主要技术概念参考以下官方页面，核对登记日期2026-10-26；这些页面可能继续更新，登记不构成专家盲审或完整质量保证。

- [Spring依赖注入](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)：构造注入、依赖方向与纯构造循环；网页当日为Spring Framework 7.0.10，发行版配置差异须另核实。
- [Redis持久化](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)：RDB、AOF与刷盘策略；故障模型、备份和恢复讨论作为候选题的推理要求，不能仅凭文档标签宣称零丢失。
- [Python 3.12 copy](https://docs.python.org/3.12/library/copy.html)：绑定、浅/深拷贝、memo与资源限制。
- [Python 3.12协程与任务](https://docs.python.org/3.12/library/asyncio-task.html)：协程对象、await、create_task、run。

来源登记在../question_bank/source_registry.json；reference_checked仅代表本批对参考资料的概念核对，不是对每个答案的独立标注。候选按当前结构通过审校，仍需检查关键词误判、完整/部分/错误回答分布和追问路径；Python拷贝题需补相应技能树子路径。本轮没有激活或重建索引。

运行与发布步骤见[维护说明](../../docs/题库审校与发布说明.md)。
