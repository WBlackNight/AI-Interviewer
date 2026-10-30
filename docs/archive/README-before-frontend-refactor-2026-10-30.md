# AI 模拟面试官（Mock Interviewer）

2026-10-29排版续批：工作区字体与阅读层级统一，实时陪练新增当前题上下文和字幕跟随开关；16页结构检查、主要页面断点检查通过。75项针对性回归及最终12项实时模块回归通过。见[本轮日志](docs/开发日志-2026-10-29-字体排版与题目陪练.md)。

2026-10-29实时语音续批：先完成同连接两轮自主回复、自然停顿（无强制commit）及取消确认检测，再新增实时陪练页面与持续S2S通道。支持双方字幕、暂停/继续和打断；陪练不自动提交正式评分。87项针对性回归通过。见[实时语音日志](docs/开发日志-2026-10-29-实时语音陪练.md)。

2026-10-29语音联调续批：确认旧版APP ID与Access Token后，真实短音频转写、指定文本合成及网页WAV→保存→追问→朗读链路通过；747项回归通过。修正独立合成事件及省略response_id的音频分片兼容，凭据仅保存在后端本机配置，不使用Secret Key。真实质量、麦克风真机和计费仍待验收。见[接入说明](docs/豆包语音接入说明.md)、[联调日志](docs/开发日志-2026-10-29-豆包旧版鉴权联调.md)。

2026-10-28功能与布局续批：任务板新增显式保存的快捷日期，修复手机计划筛选重叠，完善主题多选状态；规则评分v2修正自动执行表达漏判。713项集中回归通过，七个主要页面的1440/390布局检查通过，当前18题与候选未激活状态保持。见[本轮日志](docs/开发日志-2026-10-28-评分修正与布局巡检.md)。

首页与选择框重构：银白/青绿视觉、居中标题、产品演示窗口、分段/胶囊配置与有限动效已接入，原生选择框同步优化浅/深色、焦点和手机字号。可直接打开[本地预览](http://localhost:3000/)，无需重建；29项网关、12项原生协议及浏览器检查通过。见[页面日志](docs/开发日志-2026-10-28-首页与控件重构.md)。

2026-10-28续批：题号追问路由、18/24题成套资产准备/校验和18条作者参考示例对照已实现，693项回归与三场隔离HTTP/WS通过。现行仍18题，候选正反例揭示的规则误判尚待处理，本批零模型调用。见[进度](docs/进度评估-2026-10-28.md)、[维护说明](docs/题库审校与发布说明.md)、[开发日志](docs/开发日志-2026-10-28-题库候选与发布链路.md)。

严格评分续批：原文候选与逐命中证据校验已实现，固定错误与未知用量暂停原因可观察。669项回归通过，一次Java/BM25真实严格整场6/6调用成功，含重启恢复、重发幂等及导出；混合组合受模型网络错误阻断，重复稳定性与独立人工质量仍待验收。见[评分日志](docs/开发日志-2026-10-27-严格评分链路.md)。

原生首页：[index.html](index.html)，直接复用本地青栈雾林稿改造，无框架、无外部资源、无需重新构建。访问本机[首页预览](http://localhost:3000/)；四文件纯静态3001启动方式、文案和接口配置见[接入说明](assets/README.md)。

完整接入预览使用[同源首页入口](http://localhost:3000/)；运行`evals/native_home_preview.py`保留现有Next配置/PDF入口，支持从原生首页创建面试并进入原生练习室，使用独立离线演示库。

主流程收口：计划记录页已接入主题复盘，可查看已完成场次的主题分、实际难度与评分来源，打开报告证据，并显式加入复习任务；重复加入保持已复习状态，再从任务板进入本主题复练。647项全量及12项协议通过，仍14页、30文件。当前为离线主流程交付；模型整场质量、题库内容和生产部署按[主要交付清单](docs/主流程交付清单.md)优先验收。见[本轮日志](docs/开发日志-2026-10-27-主流程闭环.md)。

新增“计划练习记录”：从准备计划卡片进入，按未开始/进行中/已完成/已取消筛选，八项分页，刷新恢复，直接继续练习或打开报告。归档仍可回看，删除后的计数沿原规则重算。十四页原生工作区、30文件包已接通；644项回归及12项协议通过。见[本轮日志](docs/开发日志-2026-10-27-计划练习记录.md)与[记录设计](docs/计划练习记录设计.md)。

新增[准备计划](http://localhost:3000/plans)：主动选岗位、主题与强度，保存目标日期；支持编辑名称/日期、归档恢复和开始/继续计划练习，显示关联练习的完成场数。保存计划不自动创建练习，四个并发开始请求复用同一未结束场次。报告可返回指定来源计划，练习概览增加最近目标与计划计数。来源衔接见[回链日志](docs/开发日志-2026-10-27-计划回链与概览.md)、[计划设计](docs/准备计划设计.md)及[最新进度](docs/进度评估-2026-10-27.md)。

[我的题单](http://localhost:3000/library)已支持收藏关键词搜索与清除筛选，题库卡片可携带题号进入收藏，登录后可返回原题；两区域读取失败分别恢复，单条结果自适应全宽。修复离线审校空文件误报通过。见[题单衔接日志](docs/开发日志-2026-10-26-题单衔接与恢复.md)。

[题库覆盖与来源](http://localhost:3000/coverage)支持查看岗位/主题/难度数量、待补格、来源声明，导出JSON待补清单。配套离线审校工具及6道自编候选稿，当前运行仍18题，未改题库或检索索引。十二页原生工作区已接通。见[覆盖日志](docs/开发日志-2026-10-26-题库覆盖与审校.md)与[审校与发布说明](docs/题库审校与发布说明.md)。

[我的题单](http://localhost:3000/library)支持登录后收藏当前题库中的题目，按岗位及待回看/已看过筛选、分页，并可开始本主题练习。重复收藏保持标记，版本冲突不会覆盖，题目下架保留不可用提示，账户删除一并清理。见[题单日志](docs/开发日志-2026-10-26-个人题单.md)与[数据设计](docs/个人题单设计.md)。

[题库探索](http://localhost:3000/catalog)支持按岗位、主题、题目难度、关键词与题型浏览题干和来源，跨页勾选知识主题创建匿名或账户专项。浏览难度严格匹配，专项按主题出题，不锁定预览题。见[题库日志](docs/开发日志-2026-10-26-题库探索.md)，接口为GET `/api/catalog`。

[练习概览](http://localhost:3000/dashboard)及原生文字练习室支持查看今日/逾期、七日记录并继续练习；答题支持待保存提示、轮次分页、草稿保护、幂等恢复和结束后的报告入口。见[练习室日志](docs/开发日志-2026-10-25-练习室与概览.md)，接口为GET `/api/account/dashboard`。

报告与[跨场复盘](http://localhost:3000/review)已接入原生布局：逐轮主题/追问筛选、分页、完整导出、薄弱项复练、加入任务及来源回链；复盘支持岗位/主题/页码刷新恢复。586项回归通过，复用现有接口及Next练习室，无新依赖或构建。见[本轮日志](docs/开发日志-2026-10-25-报告与跨场复盘.md)与[最新进度](docs/进度评估-2026-10-25.md)。

面向 IT 求职者的技术面试演练项目。当前支持 **文字面试与 PDF 简历上传**：上传 PDF 或粘贴简历文本 → 选择岗位和难度 → 多轮回答与追问 → 查看能力维度及逐轮评分。

当前提供 Java 后端和 Python 后端两个岗位，共18道内置示例题（Java 11题、Python 7题，各含1道Python编码题）。岗位选项由服务端配置提供。支持智谱文本模型、Embedding-3与RRF混合检索，仓库零配置仍离线。LLM四组件合成探针与一次BM25严格整场零回退通过，多输入/混合组合稳定性及独立质量评测仍待验收；真实语音短样本链路已通过，质量、容量及生产部署仍需验收。

支持匿名练习及本地账户登录。登录后可认领旧匿名面试、找回账户历史、继续/复练和删除所属记录；账户会话7天到期，可主动退出。

面试页、练习记录及进行中报告可二次确认取消面试。取消保留已提交回答和部分报告，不能恢复本场，也不计入已完成记录的跨场对照；取消后可删除所属记录或账户。题库版本变化无法继续的旧面试也可取消。

新增“复习任务”板块：从所属已完成报告主动加入待补强主题与未覆盖要点，按岗位/状态筛选、分页、标记已复习或恢复待复习；重新登录仍保留。同一报告重复加入不重置进度，删除来源面试/账户同步清理任务。手动完成状态不修改评分，也不表示能力提升。

任务卡片可直接“练习本主题”，沿用原岗位与强度。未结束专项提供继续入口，重复创建请求复用同一场；结束或取消后可再练。专项报告与导出保留任务来源，练习结束不会自动标记已复习。

任务支持自定复习日期、改期/清空与今日/逾期/未来/未安排视图，统一按北京时间日历筛选。完成任务保留原定日期；改期不改变完成状态或评分。没有自动提醒。

新增[个人复习笔记](http://localhost:3000/notes)：原生HTML/CSS/JS页面，复用已有账户、复习任务和专项练习接口，无需重新构建Next.js。每项最多2,000字，显式保存、版本冲突保留草稿；可直接开始/继续本主题练习。笔记只作个人记录，不进入模型、评分或报告导出；删除来源/账户同步清理。运行上方同源预览脚本可体验，首页导航和页脚均有入口。详见[笔记开发日志](docs/开发日志-2026-10-24-复习笔记.md)。

[复习任务板](http://localhost:3000/revision)已接入相同原生视觉，支持日期安排、完成/恢复、开始/继续专项，以及新增的主题/笔记关键词搜索和有无笔记筛选。搜索仅匹配当前账户已保存内容，可与岗位、状态及日期组合，计数和分页由服务端计算。原Next任务页可经本机`/legacy-revision`回看。见[工作区开发日志](docs/开发日志-2026-10-24-复习工作区.md)。

[账户](http://localhost:3000/account)与[练习记录](http://localhost:3000/history)已接入原生布局：登录/注册、当前会话退出、账户概览、匿名记录与逐场认领、继续/报告及独立取消/删除确认均保留。记录新增岗位、强度与状态组合筛选，每页8条，账户查询由服务端执行。旧页面通过`/legacy-account`、`/legacy-history`保留。本轮584项回归通过，无新依赖或Next构建；详见[账户与记录日志](docs/开发日志-2026-10-24-账户与记录布局.md)。

- [前端美化与预览日志](docs/开发日志-2026-10-24-前端美化预览.md)：统一工作空间视觉、响应式首页、演示账户与本地预览启动方式。
- [复习日期日志](docs/开发日志-2026-10-24-复习日期.md)：日期安排、筛选、重启恢复、删除及本轮预览入口。
- [技术实现步骤](docs/技术实现步骤.md)：当前能力、修复优先级、后续实现与验收。
- [任务专项开发日志](docs/开发日志-2026-10-23-任务专项.md)：从任务开始/继续专项、并发重试去重、来源及独立删除验收。
- [复习任务板设计](docs/复习任务板设计.md)与[开发日志](docs/开发日志-2026-10-23-复习任务板.md)：账户复习清单、状态管理及浏览器/附件验收。
- [取消面试开发日志](docs/开发日志-2026-10-23-取消面试.md)：终态、评分竞态、旧资产与重启恢复验收。
- [评分来源与跨场复盘日志](docs/开发日志-2026-10-23-评分来源与跨场复盘.md)：逐轮来源、版本、重复题口径及本轮验证范围。
- [账户开发日志](docs/开发日志-2026-10-23-账户与历史.md)与[数据生命周期](docs/账户与数据生命周期.md)：登录、匿名认领、分页历史及删除规则。
- [专项复练开发日志](docs/开发日志-2026-10-23-专项复练.md)：主题选择、薄弱项复练、双岗位重启验证。
- [双岗位开发日志](docs/开发日志-2026-10-23-双岗位.md)：服务端岗位配置、Python题库与双岗位验证。
- [当前进度评估](docs/进度评估-2026-10-27.md)：已交付、未验收门槛与新功能优先级。
- [记录与复盘日志](docs/开发日志-2026-10-23-记录与复盘.md)：练习记录、继续入口、报告导出与筛选。
- [智谱LLM联调日志](docs/开发日志-2026-10-22-智谱LLM联调.md)：四组件、提示词契约修正、严格面试失败与日常回退验证。
- [智谱Embedding接入日志](docs/开发日志-2026-10-22-智谱Embedding.md)：真实API、独立索引、检索对照与重启恢复验证。
- [沙箱开发日志](docs/开发日志-2026-10-22-P3沙箱.md)：有界准入、响应限制、故障恢复及部署验证边界。
- [预算开发日志](docs/开发日志-2026-10-22-预算与并发.md)：持久化用量、业务接线、重启/重试与并发验证。
- [本轮开发日志](docs/开发日志-2026-10-21-P2.4.md)：离线索引、三种检索对照、验证结果与后续事项。
- [PDF开发日志](docs/开发日志-2026-10-21.md)：P2.3上传、隐私验证与页面证据。
- [修复记录](docs/修复记录-2026-10-10.md)：本轮修改、回归证据与升级注意事项。
- [检阅记录](docs/检阅记录-2026-10-09.md)：代码证据、已复现缺陷和本次验证结果。

## 当前能力与边界

| 模块 | 当前实现 | 生效边界 |
|---|---|---|
| 编排与恢复 | 7状态、数据库快照、轮次版本、回答幂等、原子提交 | 建议单worker；重连返回全历史，尚未做大规模性能验证 |
| 评分 | 关键词基线；LLM分数/维度/锚点/原话校验，失败可观察回退 | 原话校验不等于语义正确，仍需真人质量评测 |
| 规划 | 简历主题加权、合法LLM大纲、权重归一化 | 智谱合成探针通过；质量与更多输入仍需评测 |
| 专项与复练 | 选择知识主题；完整报告可一键复练可用薄弱主题 | 每主题最多2道主问题，无编码题；跨场可能重复，不代表能力提升 |
| 追问 | 唯一技能路径、逐层目标、独立题干和锚点；传入原回答 | 泛化效果仍需标注评测 |
| 题库 | 默认BM25，可选哈希/智谱向量及RRF；统一过滤、版本索引、故障回退 | 智谱真实调用已验证，哈希是词法基线；进行中检索版本变化需恢复原配置或新建面试 |
| 简历与访问 | 文本/PDF上传、基础PII脱敏；匿名凭据、账户归属与会话撤销 | PDF仅文本层；密码找回、分布式限流、备份/供应商删除等完整生命周期待补 |
| 账户历史 | 登录/注册、匿名面试认领、分页、继续与删除 | 连接同一后端重新登录可找回；跨场画像尚未实现 |
| 来源与跨场复盘 | 逐轮来源/版本归档；同岗位/主题的已完成记录对照 | 老记录来源未知；重复题按ID+版本核对，不推断能力提升 |
| 个人题单 | 账户收藏、手动状态、版本保护、分页、当前题目解析与主题练习 | 每账户最多500条，不保存题干副本；已看过不等于掌握 |
| 复习任务 | 主题清单、手动完成/恢复、主题专项、来源报告、自定日期与日期筛选 | 最多取报告最弱2主题、每主题最多8要点；无自动排期/提醒/能力判定 |
| 取消面试 | 匿名/账户取消、幂等终态、保留部分报告；支持旧资产无法恢复的场景 | 未提交内容不保存；其他空闲连接在下一交互或刷新时同步 |
| 编码题 | 标准输入/输出说明、6组用例、Judge0异步提交与轮询 | 未配置沙箱不执行代码；真实隔离部署待验证 |
| 报告 | 实际题干和完整回答，主问题/轮数分列，主题加权，弱项阈值 | 跨场画像与训练效果评估待实现 |

综合面试的编码题默认挂在首主题后；专项不加入编码题。收尾会直接完成面试。语音默认关闭；豆包真实识别/合成短样本已通过，质量及真机指标仍待验证。

PDF 上传前需更新依赖：在 `backend` 执行 `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`。首页选择“上传 PDF”，仅在点击开始时上传。扫描件、加密或损坏文件会提示改用粘贴文本，不提供 OCR。

## 本地启动

本次验证环境：Windows、Python **3.12.15**、Node.js **24.14.1**。依赖版本见 `backend/requirements.txt` 和 `frontend/package-lock.json`；其他运行时版本需要另行验证。以下命令使用 **PowerShell**，两个终端均从项目根目录开始。

后端（8000 端口，无需 API Key）：

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.org/simple --timeout 60 --retries 3
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

若没有 `py` 启动器，先用 `python --version` 确认解释器，再用 `python -m venv .venv`。已有可用虚拟环境时跳过创建。默认 SQLite 文件为启动工作目录下的 `dev.db`，因此后端命令统一在 `backend` 下执行。

前端（3000 端口）：

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

访问 [面试首页](http://localhost:3000)；后端 [健康检查](http://127.0.0.1:8000/api/health) 和 [交互式 API 文档](http://127.0.0.1:8000/docs) 可用于排错。

上述方式直接使用虚拟环境解释器，无需激活。需要激活时：

| Shell            | 激活命令                            |
| ---------------- | ------------------------------- |
| PowerShell       | `.\.venv\Scripts\Activate.ps1`  |
| CMD              | `.venv\Scripts\activate.bat`    |
| Windows Git Bash | `source .venv/Scripts/activate` |
| Linux/macOS Bash | `source .venv/bin/activate`     |

Linux/macOS 将示例中的解释器改为 `.venv/bin/python`，`npm.cmd` 改为 `npm`。

## 配置说明

默认不需要 `.env`。按需将 `backend/.env.example` 复制为 `backend/.env`，将 `frontend/.env.example` 复制为 `frontend/.env.local`，不要覆盖已有配置。后端 `.env` 按进程工作目录读取，设置缓存需重启进程才能更新。

| 环境变量                                      | 默认值/作用                                          | 生效边界                                 |
| ----------------------------------------- | ----------------------------------------------- | ------------------------------------ |
| `DATABASE_URL`                            | `sqlite:///./dev.db`                            | PostgreSQL 还需安装驱动并验证迁移               |
| `LLM_API_KEY`                             | 空：启发式模式                                         | 非空会选择 LLM 组件；不代表远端调用成功               |
| `LLM_BASE_URL` / `LLM_MODEL`              | `https://api.deepseek.com/v1` / `deepseek-chat` | 按实际服务商填写并联调，兼容协议不保证所有模型兼容            |
| `LLM_TEMPERATURE` / `LLM_TIMEOUT_SECONDS` | `0.3` / `60.0`                                  | 组件可覆盖 temperature；当前评分请求为 0          |
| `LLM_MAX_OUTPUT_TOKENS` / `LLM_THINKING_MODE` | `2048` / 不发送 | 有限输出；thinking仅按所选供应商支持情况显式配置，GLM-4-Flash-250414不发送 |
| `JUDGE0_URL` / `JUDGE0_API_KEY`           | 空                                               | 启用提交/轮询；服务故障保留当前轮可重试，部署仍需验证            |
| `JUDGE0_LANGUAGE_ID`                      | `71`                                            | 客户端默认 Python 3；部署后查询语言列表确认           |
| `SANDBOX_MAX_CONCURRENCY` / `SANDBOX_MAX_WAITERS` | `2` / `8` | 进程共享判题作业准入，有界FIFO等待；不是远端或跨worker全局配额 |
| `SANDBOX_QUEUE_TIMEOUT_SECONDS` / `SANDBOX_TIMEOUT_SECONDS` | `2` / `15` | 等待也计入判题总截止时间 |
| `SANDBOX_MAX_RESPONSE_BYTES` / `SANDBOX_MAX_TESTCASES` | `262144` / `12` | 单次解码HTTP响应与每作业用例上限；每用例输入/期望各64KiB |
| `PASS_SCORE`                              | `7.0`                                           | 知识题达到阈值后推进                           |
| `PROBE_DEPTH_LIMIT`                       | `3`                                             | 未达通过线时的追问上限                          |
| `MAX_PLAN_THEMES`                         | `3`                                             | 每场主题数上限                              |
| `PROBE_SCORE`                             | `4.0`                                           | 低于此分先澄清基础，否则深入；所有未通过回答均受追问上限约束                 |
| `CORS_ORIGINS`                            | `["http://localhost:3000"]`                     | JSON 数组；换前端域名或端口需更新                  |
| `QUESTION_BANK_DIR` / `SKILL_TREE_DIR`    | 根目录 `data` 下对应目录                                | 启动加载并缓存，修改数据后重启                      |
| `RETRIEVAL_PROVIDER` | `bm25`，可选`vector`/`hybrid` | 不根据API Key自动切换；后两种需独立构建索引 |
| `RETRIEVAL_INDEX_PATH` | `data/retrieval/question_index.json` | 相对项目根目录解析，与启动目录无关 |
| `RETRIEVAL_CANDIDATE_K` / `RETRIEVAL_RRF_K` | `20` / `60` | 两支路共享候选过滤；RRF按名次融合 |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` / `EMBEDDING_DIMENSIONS` | `hash` / `char-ngram-hash-v1` / `256` | 另支持`zhipu` / `embedding-3` / `256、512、1024、2048`；更改身份需独立索引 |
| `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` | 空 / `https://open.bigmodel.cn/api/paas/v4` | 仅zhipu使用；仅允许官方HTTPS端点，不跟随重定向，不自动重试 |
| `EMBEDDING_REVISION` / `EMBEDDING_TIMEOUT_SECONDS` | `1` / `15` | 运维修订参与索引身份；HTTP超时及分块读取检查，单响应上限4MiB |
| `REDIS_URL` | 预留配置 | 尚无Redis会话缓存实现 |
| `NEXT_PUBLIC_API_BASE`                    | `http://localhost:8000`                         | 前端 REST 地址                           |
| `NEXT_PUBLIC_WS_BASE`                     | `ws://localhost:8000`                           | 前端 WebSocket 地址；HTTPS 页面应使用 `wss://` |

前端公开变量不应存放密钥，发布时在构建前设置。`/api/health` 的 `llm_enabled` 和 `sandbox_enabled` 只检查配置是否非空，并不探测外部服务。

当前 `docker-compose.yml` 只启动 PostgreSQL、Redis、Qdrant，**不含前后端或 Judge0**。本地 SQLite 演示无需启动这些容器。

切换 PostgreSQL 的准备示例（尚未纳入本次实测）：

```powershell
# 项目根目录
docker compose up -d postgres
cd backend
.\.venv\Scripts\python.exe -m pip install "psycopg[binary]>=3,<4"
$env:DATABASE_URL='postgresql+psycopg://interviewer:interviewer@localhost:5432/interviewer'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

选定驱动版本后纳入依赖锁定；上述默认账号仅用于本机开发。修改连接串不会迁移 SQLite 数据。启动时使用 `create_all` 添加新表，并执行 P0.1 事件序号增量升级；正式发布仍需版本化迁移与备份。

## 验证命令

后端现有单元/组件测试（从根目录开始）：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

前端生产构建（新终端，从根目录开始）：

```powershell
cd frontend
npm.cmd run build
```

HTTP + WebSocket 冒烟支持自动选择本机端口、独立临时数据库、服务重启和自动清理（从根目录执行，必须使用已安装后端依赖的解释器）：

```powershell
.\backend\.venv\Scripts\python.exe evals/smoke_e2e.py --start-server --restart
.\backend\.venv\Scripts\python.exe evals/smoke_e2e.py --start-server --restart --pdf
```

也可连接已有8200端口服务：`python evals/smoke_e2e.py`；其他端口用 `--base-url`。`--restart` 仅能重启脚本自己的临时服务，语音参数尚未实现。

LLM 真实连通性探测（**`health` 的 `llm_enabled` 只说明配置存在，不等于可用**）：

```bash
python evals/llm_ping.py            # 退出码 0=四组件全通 1=有回退 2=未配置密钥
python evals/llm_ping.py --strict --repeat 2 --json-out docs/logs/llm-local.json
```

语音分段延迟探针：`python evals/latency_probe.py --base-url http://127.0.0.1:8211`（需先以 `VOICE_ENABLED=true` 启动）。

`llm_ping.py`始终读取`backend/.env`，逐次校验四组件并禁用评分缓存；任一次失败/回退/未知用量均不能通过。严格模式也保存脱敏报告并继续检查其他组件。仅发送合成数据，不代表真人评分质量。客户端不读取系统代理、不跟随重定向；错误日志不保存供应商正文。

进程内 LLM 分项计数与评分缓存统计：`GET /api/diagnostics/llm`（只含计数与类别，无回答/简历/凭据）。`validation_reasons`细分固定评分错误；未知用量导致预算暂停时，上游固定错误类别仍可观察。探针可选`--score-case short|mixed`验证不同合成回答，默认baseline。评分提示词当前为v7，原文候选仅辅助模型引用，不代表语义命中。

2026-10-21本轮检索改造后 **308项后端测试通过**；BM25/向量/混合三种模式均通过真实服务重启与幂等冒烟，混合模式同时覆盖PDF入口。前端本轮未修改，上一轮构建与浏览器上传验证见[PDF日志](docs/开发日志-2026-10-21.md)；本轮结果见[检索日志](docs/开发日志-2026-10-21-P2.4.md)。GitHub Actions增加索引/检索评测与冒烟，尚未在远程CI运行。

## 最新验证

2026-10-23任务专项续：**后端509项、前端34项及生产构建通过**。双岗位每任务4个并发创建请求只生成1场专项，各完成2题8轮并进程重启；任务手动状态保留，来源删除后专项独立保留。浏览器完成任务开始/继续、8轮完整专项、报告来源及两种附件下载读回，外部模型调用0。见[本轮日志](docs/开发日志-2026-10-23-任务专项.md)。

2026-10-23复习任务板续：**后端496项、前端32项及生产构建通过**；真实服务验证两场报告加入、完成/恢复、同源去重、独立登录、重启持久化和删除清理，外部模型调用0。浏览器完成新任务板、21项任务分页、24条历史分页、匿名认领及删除确认撤回；Markdown/JSON附件已实际下载并读回完整8轮内容。见[本轮日志](docs/开发日志-2026-10-23-复习任务板.md)。取消功能的483/28项验收及此前471项来源回归见[上一批日志](docs/开发日志-2026-10-23-取消面试.md)。

2026-10-23账户续：**后端459项、前端20项测试及生产构建通过**。真实服务完成认领、跨账户拦截、重新登录找回、两场账户面试的重启恢复/幂等、复练、退出和删除；匿名PDF混合检索全流程回归通过。零外部模型调用；新账户页面尚未逐项浏览器点击验收。详见[账户日志](docs/开发日志-2026-10-23-账户与历史.md)。

2026-10-23专项续：**后端437项、前端13项测试和生产构建通过**。双岗位专项及薄弱项复练共4场，均完成2道主问题/8轮回答，含4次进程重启、断线补发、独立凭据和JSON导出；原PDF综合面试回归通过。零外部模型调用。详见[专项日志](docs/开发日志-2026-10-23-专项复练.md)。

2026-10-23双岗位续：**后端420项、前端10项测试和生产构建通过**。Java/Python离线完整流程及Python真实智谱混合检索通过，重启、幂等、摘要与导出正常；当前18题。更新后须重启服务、新建面试，旧题库索引不能混用。详见[双岗位日志](docs/开发日志-2026-10-23-双岗位.md)。

2026-10-23：**后端409项、前端8项测试通过，生产构建通过**。新增练习记录、继续面试、Markdown/JSON导出及主题/待补强/追问筛选；真实HTTP/WS重启与两种附件下载验证通过。浏览器下载落盘已在复习任务板批次补验，历史记录见[该批日志](docs/开发日志-2026-10-23-记录与复盘.md)。

2026-10-22真实LLM续：**401项测试通过**；GLM-4-Flash-250414两轮四组件探针8/8通过、3620 tokens。日常回退模式整场/重启/账本恢复通过，评分2次回退；严格整场仍有`bad_payload`，未标为零回退验收通过。详见[LLM联调日志](docs/开发日志-2026-10-22-智谱LLM联调.md)。

2026-10-22智谱接入后 **382项后端测试通过**。Embedding-3真实调用、11题索引、幂等复用、10查询三策略对照及PDF+混合检索重启冒烟通过，全程零回退。本机`backend/.env`已启用1024维智谱混合检索，密钥仅在本地服务端配置；仓库默认与CI仍离线。详见[接入日志](docs/开发日志-2026-10-22-智谱Embedding.md)。

2026-10-22沙箱扩展后 **350项后端测试通过**；PDF+混合检索真实重启冒烟通过。Judge0未配置、当前环境未检测到Docker命令，真实判题与隔离未验收。详见[沙箱日志](docs/开发日志-2026-10-22-P3沙箱.md)。

2026-10-22预算接线后全量 **321项测试通过**，PDF+混合检索真实重启冒烟通过；本轮前端未修改。最新说明见[预算日志](docs/开发日志-2026-10-22-预算与并发.md)。

## 模型用量与并发

本机`backend/.env`已配置智谱文本模型，单次最多2048输出tokens、1次尝试、1个在飞请求、每资源20000 tokens软预算，评分缓存关闭，日常严格模式关闭。原有服务需重启，新建面试使用新配置。运行时仍可能因模型输出不合规而回退；不要把流程完成当作全部评分来自模型。

真实整场验证显式使用`--llm`，默认强制严格模式；也可显式验证回退后的业务流程。两种报告分列，不会把回退标成模型成功：

```powershell
.\backend\.venv\Scripts\python.exe evals/smoke_e2e.py --start-server --restart --pdf --llm --retrieval hybrid --embedding-provider zhipu --dimensions 1024 --index-path data/retrieval/zhipu-multi-position-v1.json --json-out docs/logs/llm-strict-local.json
# 若只验证日常回退流程，加 --allow-llm-fallback，并检查报告中llm.all_llm_success。
```

真实LLM冒烟将合成面试限制为1主题、最多1层追问，首答故意不完整以触发追问；验证四组件、已知用量、重启恢复及重发不重复用量。脚本默认仍不启用LLM。失败报告只保存类别、诊断计数及临时账本合计，不保存密钥或完整异常正文。

`LLM_MAX_CONCURRENCY`控制所有客户端共享的**进程级**在飞模型请求，不是跨worker/主机全局配额。`LLM_BUDGET_TOKENS_PER_INTERVIEW`（默认0不限）、可选金额阈值分别应用于每份简历和每场面试；规划与后续评分/追问共用面试账本，简历解析单独计量。金额阈值必须同时配置`LLM_PRICE_INPUT_PER_MILLION`与`LLM_PRICE_OUTPUT_PER_MILLION`，只按配置计算，不代表供应商账单。

启动新增`llm_budget_usage`表，不改已有业务列。账本独立提交，轮次失败/回滚不撤销已发生用量；已提交回答重发不重复调用。资源首次使用模型时冻结限额、单价与模型身份，后续修改环境不会重置旧资源额度；更换模型/服务地址须恢复原配置或创建新面试。

预算是**软阈值**：每次尝试前检查，按响应usage记账，单次请求可越线，后续请求阻止。空响应重试也记账。缺失usage、网络失败或崩溃遗留pending不视为免费；启用预算时暂停后续调用，核账后再恢复。未限制预算时允许原有有限重试，同时记录未知次数。实际平台账单硬封顶仍应使用供应商配额；新建资源不能替代账户总额限制。

读取`GET /api/interview/{id}/usage`须带`X-Interview-Token`；简历`GET /api/resume/{id}/usage`须带`X-Resume-Token`。响应有已知token、未知次数、pending和version，不包含提示词/回答/密钥。未知用量恢复须先停止旧worker、核实供应商资源累计用量，再从backend目录运行`python ../evals/reconcile_llm_usage.py --help`按CAS版本核账；不能降低已知用量，不能用猜测值清账。

## 沙箱判题与验收

`GET /api/diagnostics/sandbox`只返回配置与本机准入状态，`execution_verified=false`，不主动联系Judge0。所有客户端共享进程级判题作业准入；队列满/等待超时在提交前拒绝。客户端超时不会撤回已接受的远端程序，远端容量仍依赖Judge0 worker与队列限制。

HTTP 429、配置错误、传输/内部故障与候选人的WA/TLE/编译/运行错误分开处理。基础设施失败返回`sandbox_*`错误，保留原轮次与版本，不记零分；重试可能再次调用LLM，已发生用量不会回滚。响应按块读取并限制体积，stdout保存前基本脱敏，仅保存前200字符。

从根目录运行真实探针（必须先由管理员准备隔离的Judge0并配置JUDGE0_URL）：

```powershell
.\backend\.venv\Scripts\python.exe evals/sandbox_probe.py --output sandbox-config-check.json
# 显式执行4个合成Python程序：正确、错误、超时、语法错误
.\backend\.venv\Scripts\python.exe evals/sandbox_probe.py --execute --output sandbox-execution-check.json
```

无配置退出2；失败退出1；只读配置检查通过或显式执行通过退出0，须同时查看`execution_verified`。检查配置或4个程序成功都不证明隔离有效；部署/外联/资源验收步骤见[Judge0部署验收](docs/Judge0部署验收.md)。不会在宿主Python执行用户代码。

## 离线索引与混合检索（运行命令）

使用默认hash配置时，从项目根目录运行，无需新增依赖、API Key或模型下载。建索引和评测脚本读取`backend/.env`，若选择zhipu会实际调用远程API：

```powershell
.\backend\.venv\Scripts\python.exe evals/build_question_index.py
# 同一资产再次运行返回unchanged；修改题库/模型参数后使用新路径或--rebuild
.\backend\.venv\Scripts\python.exe evals/retrieval_eval.py --output docs/logs/retrieval-local.json
.\backend\.venv\Scripts\python.exe evals/smoke_e2e.py --start-server --restart --pdf --retrieval hybrid
.\backend\.venv\Scripts\python.exe evals/smoke_e2e.py --start-server --restart --retrieval vector
```

后端默认仍为BM25。需要尝试离线混合模式时，在`backend/.env`设置`RETRIEVAL_PROVIDER=hybrid`（或vector），先运行建索引命令，再启动服务。启动只加载并校验索引，不自动计算文档向量。模型/维度/题库变动会使旧索引失效；缺失或失效时明确记录回退，继续使用BM25。`GET /api/diagnostics/retrieval`提供当前模式、索引状态和成功/回退计数；启用配置本身不表示向量支路已成功运行。

索引记录题目ID、来源、岗位、主题、难度、题型、题目摘要及模型/修订/维度/L2归一化/余弦度量；同一版本重复构建不改写文件。新文件完整生成后原子替换，构建失败保留原索引。当前JSON索引面向小型题库，文件上限32MiB；不是生产向量数据库。

会话快照冻结检索模式/索引/融合参数，切换后进行中面试须恢复原配置或新建。旧BM25快照仍可恢复。当前面试选题查询以主题/难度为主，尚未加入简历全文语义检索。

对照集见[data/evals](data/evals/README.md)，仅10条开发者合成标注。原始结果见[检索评测](docs/logs/2026-10-21/retrieval-eval.json)：本次BM25的Recall@3=0.95，哈希向量0.75，RRF混合0.90；这只是smoke结果，不代表独立质量结论，因此未切换默认策略。

### 智谱Embedding-3

在本地`backend/.env`设置`EMBEDDING_PROVIDER=zhipu`、`EMBEDDING_MODEL=embedding-3`、`EMBEDDING_DIMENSIONS=1024`、`EMBEDDING_API_KEY`和独立的`RETRIEVAL_INDEX_PATH=data/retrieval/zhipu-multi-position-v1.json`；完整样例见`.env.example`。密钥独立于`LLM_API_KEY`，接入Embedding不会自动启用LLM评分/规划。

```powershell
.\backend\.venv\Scripts\python.exe evals/embedding_ping.py
.\backend\.venv\Scripts\python.exe evals/build_question_index.py
.\backend\.venv\Scripts\python.exe evals/retrieval_eval.py --output docs/logs/retrieval-zhipu-local.json
.\backend\.venv\Scripts\python.exe evals/smoke_e2e.py --start-server --restart --pdf --retrieval hybrid --embedding-provider zhipu --dimensions 1024 --index-path data/retrieval/zhipu-multi-position-v1.json
```

索引验证后设置`RETRIEVAL_PROVIDER=hybrid`并重启后端，新建面试使用新策略。冒烟默认强制hash，远程验证必须显式传`--embedding-provider zhipu`和匹配索引/维度。查询前基本PII脱敏；当前业务发送主题/难度或编码题查询，构建发送内置题目的主题/题干。基本脱敏不保证移除所有个人信息，扩充题库时应先审阅数据。

检索诊断增加`semantic_model`及`embedding_usage`：进程内累计请求、供应商返回token和未知用量，不含查询/密钥。它独立于LLM账本，不持久化，不受LLM每场预算控制；未配置单价不推算金额，实际费用以智谱账单为准。10查询结果见[真实检索评测](docs/logs/2026-10-22/zhipu-retrieval-eval.json)：BM25/智谱向量/混合Recall@3为0.95/1.00/1.00，仅为冒烟证据。

## REST 与 WebSocket 协议

未登录时，“练习记录”显示当前标签页最多50场匿名面试；关闭标签页后匿名凭据不再保留。登录后显示服务端账户历史，每页20条，可分页、继续、查看报告和删除。账户历史保留至主动删除，重新登录可找回；原匿名面试需凭本标签页的匿名令牌逐场认领，认领后原令牌失效。报告支持主题、待补强和追问筛选，导出始终包含完整授权报告，进行中导出明确标为部分报告。

新增`GET /api/interview/{id}`摘要和`GET /api/interview/{id}/report/export?format=markdown|json`附件，均要求`X-Interview-Token`；读取和导出不调用模型。前端单元测试在frontend运行`npm.cmd test`。

`POST /api/interview/{id}/cancel`使用同一`X-Interview-Token`（匿名凭据或所属账户会话），无需请求体。响应包含`status=cancelled`、`changed`、`version`及`report_url`；重复取消不增加事件或版本。已完成面试返回409。取消事务提升运行版本，取消先提交时丢弃在途评分，评分先提交时保留该轮。JSON报告的`is_terminal=true, is_complete=false, is_cancelled=true`区分取消与完整完成，Markdown标为“已取消（部分报告）”。外部请求若已发出可能继续产生用量，取消不退款、不清空账本。自己的页面取消后关闭连接，其他空闲连接在下一交互或刷新时同步。

隔离取消链路复现（合成数据、外部调用0）：

```powershell
.\backend\.venv\Scripts\python.exe evals/cancellation_smoke.py --json-out docs/logs/cancellation-local.json
```

### 账户与长期历史

顶部“账户”提供注册、登录和退出；用户名3–32位ASCII字母/数字/下划线，密码12–128字符，当前没有密码找回。会话最长7天，凭据仅存在sessionStorage，关闭标签页后需重新登录。跨设备访问同一后端并登录即可读取服务端历史；本轮以独立登录会话的HTTP/WS验证该链路，未完成多设备浏览器实测。

创建文本/PDF简历或面试时，带`Authorization: Bearer <账户会话>`可自动归属账户；响应为`account_owned=true, access_token=null`。账户资源的`X-Interview-Token`/`X-Resume-Token`与WS子协议使用所属账户的有效会话，前端自动处理；其他账户被拒绝。未登录创建仍返回独立匿名资源令牌，原流程兼容。账户复练继承来源归属，匿名复练仍签发独立资源令牌。

认领页面在“练习记录”中，操作仅认领选中面试，不连带原简历或其他记录。记录删除需二次确认；账户删除需再次输入密码。进行中的面试不可删除，需先完成或取消。删除数据库中的回答、评分、事件、快照及关联授权；账本计数、既有备份和外部供应商副本的边界见[生命周期规则](docs/账户与数据生命周期.md)。

本轮新增`account/account_session/resource_owner`三表，无既有列变更；重启后端自动建缺失表，原匿名记录不自动变为账户。未改写本机密钥、题库或向量索引。复现隔离账户流程：

```powershell
.\backend\.venv\Scripts\python.exe evals/account_smoke.py --json-out docs/logs/account-local.json
```

账户接口使用`Authorization: Bearer <账户会话>`：

| 方法 | 路径 | 契约 |
|---|---|---|
| POST | `/api/auth/register`、`/api/auth/login` | JSON username/password；返回account、access_token与expires_at |
| GET | `/api/auth/me` | 返回当前账户id/username |
| POST | `/api/auth/logout` | 撤销当前会话，不撤销其他设备会话 |
| GET | `/api/account/interviews?offset=0&limit=20` | 返回items/total/has_more；limit为1–50 |
| POST | `/api/account/interviews/{id}/claim` | JSON access_token为该面试原匿名令牌；同账户重复认领幂等 |
| DELETE | `/api/account/interviews/{id}` | 删除所属的已完成/已取消/尚未开始面试；进行中409 |
| DELETE | `/api/account` | JSON password，再验证后删除账户及所属内容；存在进行中面试409 |

账户/资源响应均不缓存。账户接口输入校验不回显密码或令牌；登录/注册与账户删除有每来源每分钟20次、2个密码派生并发的进程级准入，尚非多worker全局限流。

### 复习任务板

顶部“复习任务”进入`/revision`，默认显示待复习；可切换已复习/全部任务及岗位，分页每页20项。卡片显示来源主题均分、未覆盖要点及完成时间，提供原报告入口和手动完成/恢复。统计按岗位筛选计算，不受任务状态筛选影响。页面刷新默认回到待复习/全部岗位，但任务完成状态来自数据库。

所属完整报告有薄弱主题时，可点击“加入复习任务”。服务端沿用报告口径：严格低于`WEAK_SCORE`的最弱2主题，同一主问题各轮先平均、主题内主问题等权。每主题去重保留最多8个未覆盖要点，每项最多300字符；不复制原回答、题干或简历，不调用模型。匿名报告需先登录并在练习记录页认领；进行中或取消报告不能生成任务。无待补强主题返回422。

所有任务接口使用`Authorization: Bearer <账户会话>`：

| 方法 | 路径 | 契约 |
|---|---|---|
| POST | `/api/account/interviews/{id}/revision-tasks` | 无需请求体；从服务端报告派生，返回items/added/existing；跨账户403，未完成409 |
| GET | `/api/account/revision-tasks?status=todo&offset=0&limit=20` | status可选todo/done，省略表示全部；可选position；limit为1–50；返回items/counts/positions/total/has_more |
| PATCH | `/api/account/revision-tasks/{id}` | JSON仅status=todo或done；他人或不存在任务404；重复设置不改变完成时间 |
| POST | `/api/account/revision-tasks/{id}/practice` | 无需请求体；返回原创建面试字段、revision_task_id和reused；只使用任务主题及原岗位/强度；未结束的同源专项复用 |

新增`revision_task`表，重启后端自动建缺失表，不改已有列，不自动为历史报告建任务；重建/重启前端使新页面生效。删除来源或账户与任务清理在同一事务中完成。只提供手动复习安排，尚无任务排期、提醒或自动掌握判定。详见[设计说明](docs/复习任务板设计.md)。隔离复现：

```powershell
.\backend\.venv\Scripts\python.exe evals/revision_smoke.py --json-out docs/logs/revision-local.json
```

任务专项补充：新建前校验当前岗位和知识主题可用性，已移除/无题/编码主题返回422，不放宽为综合面试；他人/不存在任务404，过期会话401。新场归当前账户，无匿名凭据，不复制原简历、回答或评分。每主题最多2主问题、保留追问，不加入编码题；跨场可能重复。任务处于已复习也可继续练习，其手动状态和完成时间保持不变。

同一任务有created/running专项时返回同一场`reused=true`，不会重新生成大纲；旧场如因题库变化无法恢复，可取消后再建。结束/取消后再点击会创建新场。新增`revision_practice`关联表，与新场/快照/账户归属同事务写入。任务列表的`latest_practice`显示最新一场，报告`revision_source`和Markdown/JSON包含原报告/任务来源。删除原报告清除任务和来源关联，已经创建的专项作为独立账户记录保留；删除专项清除对应关联；删除账户清除全部所属内容。升级后重启后端补表，无既有列变更。隔离验证：

```powershell
.\backend\.venv\Scripts\python.exe evals/revision_practice_smoke.py --json-out docs/logs/revision-practice-local.json
```

### 评分来源与跨场复盘

登录后在“练习记录”点击“同岗位跨场复盘”，进入`/review`。只对照当前账户已完成且有评分的面试；岗位/主题选项来自实际历史，不依赖当前题库是否仍保留该主题。接口默认20场、最多50场，原生页面每页4场，每张卡片对应一场面试的一个主题，均分继续按“主问题内各轮均值→同主题主问题等权”计算。显示请求强度、实际主问题难度、题数/轮数及评分来源/版本；窄屏顺序单栏，主题/页码刷新恢复。原Next表格页经本机`/legacy-review`保留。

`GET /api/account/review?position=java_backend&theme=MySQL&offset=0&limit=20`使用账户Authorization，返回positions、items、total、session_count及has_more。省略position时选择账户历史中的首个岗位，省略theme时列该岗位全部主题；总数/分页单位是面试场数。数据只含汇总和来源版本，不含原回答、题干或凭据，不调用模型。删除来源场后，对照与重复题统计按当前仍保留的记录重算。

新评分持久化`scoring_origin`：heuristic（规则）、llm（模型）、heuristic_fallback（模型失败后规则回退）、unknown（未记录）。归档评分器/配置版本、模型、提示词版本/摘要、缓存标记、回退错误类别和是否客观判题合分；题目及主问题版本仅存摘要。命中评分缓存仍是模型来源，但明确标记本轮未调用评分模型。旧评分没有来源行时保持unknown，不用当前模型配置回填。逐轮报告、JSON和Markdown导出包含来源信息；JSON保留题目版本摘要。

重复题只统计本账户另一已完成面试中，在当前主问题首次作答之前出现的同ID、同完整题目版本的主问题；不把追问轮数当重复题数。缺失旧版本时单列“版本未记录”，不判定为新题或重复题。不同题目、难度、来源及版本会影响分数，页面提供记录对照，不输出能力提升曲线或训练有效性结论。

本轮新增`score_origin`表，无旧列变更。来源与评分在同一轮事务提交，幂等补发不新增来源；记录/账户删除同时删除来源行。重启前后端补表并启用新页面，不需重建向量索引。

### 主题专项与薄弱项复练

首页选择“主题专项”，选择当前岗位1至`MAX_PLAN_THEMES`个知识主题（默认最多3个），无需简历。每主题最多2道主问题，主题等权，保留动态追问；题目耗尽不会切到其他主题或编码题，同场不重复，跨场可以重复。指定难度没有候选时沿用同主题难度放宽规则。

完成面试后，报告中有可用薄弱知识主题时出现“开始薄弱项复练”。服务端从该报告的`weak_points`筛选当前仍有知识题的根主题，保留原岗位、强度创建新面试；匿名场签发独立凭据，账户场继承归属。不复制简历、回答或评分。未完成返回409，无可复练主题返回422。创建专项/复练不调用LLM规划；实际选题仍使用已配置检索，评分和追问仍使用现有配置，启用智谱时这些环节可能产生外部调用。

```powershell
.\backend\.venv\Scripts\python.exe evals/practice_smoke.py --json-out docs/logs/practice-local.json
```

该脚本自启隔离数据库服务，使用hash混合检索和规则评分，验证Java/Python专项、复练、进程重启与幂等，默认索引须先按离线配置构建。新功能沿用现有数据库大纲和快照，无新增列、无需重建题库索引。重启前后端后使用新入口。

| 方法   | 路径                           | 输入/返回                                                                          |
| ---- | ---------------------------- | ------------------------------------------------------------------------------ |
| GET  | `/api/health`                | 状态、组件配置标记、题目数量                                                                 |
| GET  | `/api/positions`             | 岗位ID、名称、根主题、题数及`practice_themes`/`practice_theme_limit` |
| GET | `/api/diagnostics/retrieval` | 检索模式、索引/模型身份、成功/回退计数；不返回查询或个人信息 |
| POST | `/api/resume`                | JSON：`name`（最多 64 字符）、`resume_text`（非空，最多 20000 字符）；返回简历/用户 ID 及抽取字段           |
| GET | `/api/resume/limits` | PDF字节、页数、文本字符限制及OCR支持标记 |
| POST | `/api/resume/pdf` | multipart：一个 `file`（application/pdf、.pdf）和可选 `name`；返回与文本入口相同的字段和资源凭据 |
| POST | `/api/interview`             | JSON：`position`、`difficulty`，可选`resume_id`；提供`themes`数组创建专项（不能同时带resume_id），空/重复/跨岗位/编码主题返回422 |
| POST | `/api/interview/{id}/practice` | 带来源`X-Interview-Token`，无请求体；服务端根据完整报告创建薄弱主题新面试，返回新凭据、大纲和WS路径 |
| GET  | `/api/interview/{id}/report` | 面试状态及评分报告，`practice_themes`为可复练主题；部分报告该字段为空 |

匿名创建简历和面试返回独立`access_token`，前端存入当前标签页sessionStorage。账户归属创建返回`account_owned=true`、`access_token=null`，通过登录会话访问。关联简历需`X-Resume-Token`，报告需`X-Interview-Token`；匿名令牌仅限对应资源，账户会话仅限所属资源。

PDF原文件仅经有界内存和进程管道传递，不保存文件名或原文件。提取后的文本在规则/LLM解析与保存前脱敏；数据库`raw_text`同样为脱敏文本。当前正则覆盖手机号、邮箱和18位身份证，不覆盖姓名、地址等全部PII。默认上传30秒、解析10秒，进程超时被终止，每worker最多同时解析两份文件；页数/文本超限返回413，格式/无文本/加密返回422，超时408，繁忙429，解析进程不可用503。

PDF配置见 `backend/.env.example`：`RESUME_PDF_MAX_BYTES`、`RESUME_PDF_MAX_PAGES`、`RESUME_PDF_MAX_TEXT_CHARS`、`RESUME_PDF_TIMEOUT_SECONDS`、`RESUME_UPLOAD_TIMEOUT_SECONDS`。生产环境仍需网关请求体限制、应用并发配额与容器内存限制。

WebSocket 使用子协议列表 `["interview", access_token]` 传递匿名资源令牌或所属账户会话，服务端选择`interview`；浏览器Origin须在CORS名单中。凭据不放URL。连接接收消息及轮次提交前重新校验，认领/退出/到期后旧授权不能继续提交。

连接 `/ws/interview/{id}` 后发送：

```json
{"type":"start"}
```

返回 `snapshot`，含 `state`、`finished`、`version`、`current_question` 和带 `seq/version` 的历史 `events`。首次连接也返回快照。回答须绑定快照中的当前轮次与版本：

```json
{"type":"answer","message_id":"唯一消息编号","turn_id":"当前问题的32位轮次ID","version":1,"text":"回答文本","code":"仅编程题可选"}
```

同一消息编号和内容重发返回原事件；更换内容却复用编号会拒绝。过期轮次或版本不能用于新题。前端发送后锁定输入，断线重连先同步快照，待提交消息沿用原编号安全重试。

下行包含 `snapshot/state/greeting/question/answer_ack/score/agent_message/closing/report_ready/error`。ACK与score使用实际追问ID和turn_id；ACK保存可回放的回答。

### 语音链路（P1，默认关闭）

`VOICE_ENABLED=true` 时启用。上行：

```json
{"type":"audio","turn_id":"当前问题轮次ID","seq":0,"format":"pcm_s16le","sample_rate":16000,"channels":1,"data":"<base64>"}
{"type":"audio_end","turn_id":"当前问题轮次ID"}
{"type":"interrupt","utterance_id":"可省略"}
```

音频规格固定为 **16kHz/单声道/PCM s16le/100ms 帧**（1600 样本 = 3200 字节 = base64 4268 字符）；服务端不做重采样，非 16k 输入必须由客户端转换。

下行新增 `asr_partial/asr_final/tts_chunk/tts_end/barge_in_ack/voice_gap/voice_empty/voice_error/voice_cancelled`。`tts_chunk` 为 **PCM**（`sample_rate` 在帧头明示，不默认等于 ASR 采样率），前端转 Float32 写入有界播放缓冲——**不把压缩流分片逐片喂 `decodeAudioData`**（该 API 要求完整文件数据）。

关键行为：

- **前置音频缓冲**：VAD 确认（默认最短语音 200ms）前的音频帧会补进识别输入，避免丢首字；`seq` 出现缺口会重置该段缓冲并发 `voice_gap`，不静默丢音频。
- **final 单次提交**：同一 turn 的识别结果只提交一次；识别文本复用既有 `answer` 流程（幂等、版本校验、脱敏一并继承）。
- **三任务架构**：接收、业务处理、音频发送相互独立，长评分期间仍能收到 `interrupt`；每轮挂取消令牌，被取消的轮次结果按过期丢弃并落库。
- **打断**：取消当前 utterance 的播放队列并丢弃迟到分片；已写入 socket 的在途帧由前端在收到 `barge_in_ack` 时清空缓冲兜住。播放状态与面试业务状态**完全分离**。
- **背压**：音频发送队列有上限，客户端消费不过来时按超时放弃该 utterance 并记录原因，内存不无限增长。

`VOICE_*` 系列配置见 `backend/.env.example`。默认 `provider=dummy`：**DummyASR/DummyTTS 只验证协议与管道，不具备真实识别能力，不产生任何质量结论**；豆包真实供应商的配置及最新验收边界见[接入说明](docs/豆包语音接入说明.md)，质量和容量仍按技术文档单独验收。

文本回答最多20000字符，代码最多16KiB UTF-8，默认消息最多100000字节、每连接每分钟60条、闲置300秒后断开。`WS_MAX_MESSAGE_BYTES`、`WS_IDLE_TIMEOUT_SECONDS`、`TURN_TIMEOUT_SECONDS`可配置；整体轮次超时在供应商调用返回后检查，不会强制中止同步线程。

基础脱敏在简历/回答进入LLM和数据库前处理手机号、邮箱、18位身份证号；不承诺消除姓名、地址等全部个人信息。关键词评分和原话校验不能替代真人质量评测。

## 数据与扩展

核心目录：`backend/app/agent`（规划/编排/评分/追问）、`rag`（简历与题库）、`api`（REST/WS）、`sandbox`（Judge0 客户端）、`services`（报告）、`voice`（音频/VAD/ASR/TTS/播放，P1）；`frontend/app`（三个页面）、`hooks`（WS 与语音通道）、`components`（SVG 雷达图、语音面板）、`public/worklets`（采集与播放 AudioWorklet）；`data`（JSONL 题库/YAML 技能树）；`evals`（文字冒烟 + 语音延迟探针）。

新增岗位需添加匹配position的技能树和题库，首页通过服务端岗位接口自动发现，再跑全流程验证。题目ID必须唯一，知识题主题对应根节点；技能以完整路径寻址，同名短名称存在歧义时返回空。

题库是内置示例，未核验外部真题来源/许可。启动会更新数据库同ID题目；实际检索使用JSONL缓存，修改后重启。会话快照保存题库/技能路径摘要、计划和策略，进行中资产变化会拒绝继续，避免悄悄更换评分标准。已完成报告不受该检查阻碍。

报告按“同一主问题内各轮均值→同主题内主问题等权→大纲主题加权”聚合；编码主题采用规划主题的平均权重。`question_count`为独立主问题数，`answer_count`为评分轮数；弱项只取低于 `WEAK_SCORE`（默认7）的至多两个主题。沙箱合分同步进入技术深度和岗位匹配维度，表达维度保留主观评审。

首次启动升级会补缺失的运行快照、提交去重、轮次关联、资源凭据及账户/会话/归属表；有重复序号的历史事件会按行ID重排，记录仍保留。升级前建议备份数据库，正式部署应停掉旧版本服务后执行升级。没有资源凭据/恢复快照的更早记录不能自动认领，网页请创建新面试，原数据仍在数据库中。不要混跑新旧版本。

`create_all` 只建缺失的表、**不会演进已有列**，因此对列级变更另做显式迁移。启动时按「先补 schema、再修历史数据」执行：`upgrade_interview_user_nullable`（把 `interview.user_id` 改为可空以支持匿名面试；SQLite 走表重建，全程单事务并做 `foreign_key_check` 自检，幂等）→ `upgrade_event_sequences`（修历史事件序号）。两者都只作用于已存在的旧库，新库自动跳过。

## 排错

| 现象                               | 检查与处理                                                          |
| -------------------------------- | -------------------------------------------------------------- |
| pip 403 / `versions: none`       | 检查源、代理、证书和完整日志；不能仅凭报错认定一定是代理白名单                                |
| `pydantic-core` 构建失败             | 核对解释器、平台和依赖 wheel 兼容性；优先复用已验证的 Python 3.12 环境                  |
| PowerShell 阻止脚本                  | 使用上述直接解释器与 `npm.cmd` 命令，无需修改系统执行策略                             |
| 本地 HTTP 502                      | 检查代理；必要时给本机地址设置 `NO_PROXY=localhost,127.0.0.1`；冒烟 HTTP 已显式绕过代理 |
| WS 连接失败                          | 核对端口、`NEXT_PUBLIC_WS_BASE`、HTTP/HTTPS 协议以及后端日志                 |
| 测试 PermissionError / 构建找不到实际存在文件 | 先确认沙箱或文件访问权限；不要直接改业务代码掩盖环境问题                                   |
| 创建面试报 500 / `NOT NULL constraint failed: interview.user_id` | 旧库 schema 未升级。启动会自动迁移；若迁移失败，删除 `backend/dev.db` 让其按当前模型重建（会丢开发数据，建议先备份） |
| 旧库升级后想回退                     | 升级前会保留备份 `backend/dev.db.bak-*`；停服务后用备份覆盖 `dev.db` 即可              |

## 后续路线

已落实：**P0.1 核心正确性与会话恢复**、**P1 语音链路的协议、管道与前端通路**
（[P1 记录](docs/P1实现记录-2026-10-12.md)）、**P2 步骤 2.1 LLM 加固与可观测回退 + 步骤 2.2 评分证据与质量**
（[P2 记录](docs/P2实现记录-2026-10-12.md)），以及 **P2.3 PDF简历上传与基础脱敏链路**（[开发日志](docs/开发日志-2026-10-21.md)）。工程经验与编码规约见 [错误经验总结](docs/错误经验总结.md)。

**P2.4离线链路、智谱Embedding-3及预算持久化/进程并发业务接线已实现**。P2后续：独立检索标注评估、严格整场LLM输出稳定性、跨进程总配额和完整数据生命周期。
评分质量只有结构化校验，**没有任何质量结论**（κ 需多人盲评数据，见 P4）。

后续：P3 沙箱判题、P4 评测体系、P5 部署与用户验证。阶段门槛及尚未创建的文件见技术实现步骤。
P0/P1/P2 部分步骤的测试通过不代表整体已完成。

**已明确未具备的能力**（必须与上面区分开）：

- 豆包 ASR/TTS 已接入且短样本链路通过；VAD 阈值未用录音标注校准；浏览器语音未真机验证；打断延迟无实测。
- 真实LLM四组件合成探针已通过，严格整场仍有输出校验失败；独立评分与追问质量尚未验收。未配置密钥时`llm_ping.py`退出码2表示未测试。
- 评分缓存默认关闭；缓存命中不构成可重复性证据。
- 智谱向量、本地账户、来源归档与跨场记录对照已实现；自动能力画像、密码找回、生产身份审核与发布仍待完成。离线哈希不代表语义能力，PDF不含OCR和完整PII识别。
