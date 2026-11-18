# AI Interviewer · 青栈 QINGZHAN

云端部署、只有公网IP时的HTTPS和语音配置见 [部署操作步骤](deploy/cloud/README.md)。云端使用compose.cloud.yml，打包不携带任何实际API密钥或用户数据库。

AI模拟面试与复习工作区，支持文字与语音作答、逐轮报告、准备计划和复习笔记；运行题库120题，Java、Python、市场营销、运营管理、教育教学与英语面试六个方向各20题。

## 评委后台体验

| 项目 | 信息 |
| --- | --- |
| 登录账号 | `admin` |
| 后台入口 | 本机演示启动后打开 [管理工作台](http://localhost:3222/admin) |
| 权限 | 隔离演示管理员，可查看数据、审校题库、导出和处理社区举报 |
| 密码 | 通过评审专用渠道提供。本机首次启动时输入此密码，也可自行设置演示密码 |

安装下方快速运行所需的 Python 依赖后，在仓库根目录执行：

```sh
python tools/reviewer_admin_demo.py
```

Windows 可使用 `.\backend\.venv\Scripts\python.exe` 代替 `python`。演示服务仅监听本机，使用独立 SQLite 库并关闭外部 API。若需要在公网使用评委后台，请按[云端评审配置](docs/参赛API配置与密钥管理.md#创建评委体验账号)授权独立账号。

## 快速运行

需要 Python 3.12。项目包含生成后的页面资源，离线体验不需要供应商密钥。修改 React 源码时再使用 Node.js 24 安装并构建前端。

Windows PowerShell，在仓库根目录执行：

```powershell
py -3.12 -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\backend\.venv\Scripts\python.exe tools/project.py serve --offline --port 3000 --database backend/competition-demo.sqlite3
```

Linux 或 macOS，在仓库根目录执行：

```sh
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
backend/.venv/bin/python tools/project.py serve --offline --port 3000 --database backend/competition-demo.sqlite3
```

打开 [本机首页](http://localhost:3000/)。从首页开始一场文字练习可直接检查题目、追问与报告。注册后可体验小青的本地学习指引、个人记录和社区互动。实际语音、外部大模型和邮件需要服务端配置。


## 技术架构

页面与工作区采用原生 HTML/CSS/JS。文字练习室、小青与管理工作台使用 React 18、TypeScript 和 Vite 独立构建。FastAPI 同源提供页面、业务 JSON、SSE 与 WebSocket。SQLAlchemy 与 SQLite 保存会话及业务记录，题库与技能树是版本化的本地文件。云端由 Caddy 提供 HTTPS 并代理到 FastAPI。

| 评审材料 | 说明 |
| --- | --- |
| [参赛技术文档](docs/参赛技术文档.md) | 需求、架构、AI 方案、功能、创新、验收和部署 |
| [API 配置与密钥管理](docs/参赛API配置与密钥管理.md) | 离线模式、外部服务、故障定位和发布检查 |
| [环境模板](backend/.env.example) · [云环境模板](deploy/cloud/app.env.example) · [前端模板](frontend/.env.example) | 真实密钥只在服务端环境中填写 |
| [Python 依赖](backend/requirements.txt) · [前端锁文件](frontend/package-lock.json) | 首次安装使用固定依赖，前端使用 `npm --prefix frontend ci` |

## 团队信息

| 项目 | 信息 |
| --- | --- |
| 团队名称 | |
| 参赛成员 | |
| 指导教师 | |

仓库维护账号为 [WBlackNight](https://github.com/WBlackNight)。

当前结构与验收见[报告驱动重构记录](docs/报告驱动重构与验收-2026-11-15.md)。从 /roles 选择练习方向，首页可预览主题与题量，结束后回看能力表现和优先补强建议。个人概览可按最近已完成练习生成复习重点，并通过配置链接继续练习。

新增`/assistant`小青助手：结合题库资料解释知识、整理回答与推荐练习，支持真实流式生成、受限只读工具、多轮对话和账户历史。实现与竞赛改进排序见[小青助手与优先级](docs/竞赛优先级与小青助手-2026-11-16.md)。

新增`/admin`后台工作台：运营指标、趋势图表、练习/题库/用户摘要，支持筛选、排序、CSV导出、版本化审校和操作记录。服务端通过`ADMIN_ACCOUNT_IDS`、`ADMIN_VIEWER_ACCOUNT_IDS`分配管理员与只读角色，默认拒绝访问。详见[后台评估与实施清单](docs/后台差距评估与优先级执行-2026-11-17.md)。

## 开发入口

面试社区入口为 `/forum`。身份记录、帖子互动、搜索与举报审核见[面试社区产品与接口设计](docs/面试社区产品与接口设计.md)。

首次打开普通首页时，未登录访客会看到可跳过的新手指引。题库、练习室、报告、小青、账户与社区等页面首次进入时展示轻提示，各页可通过「本页指引」查看操作步骤。完成或跳过后，本浏览器按页面记住选择。使用指南提供常用页面的直达入口。各页内容集中维护于 [ui/onboarding.json](ui/onboarding.json)。登录、注册与找回密码使用本地竹叶背景资源。

同源启动可使用 python tools/project.py serve --port 3000，读取 backend/.env 并沿用既有数据库配置。跨机器迁移及模块职责见[代码结构与迁移指南](docs/代码结构与迁移指南.md)。

日常操作统一使用`python tools/project.py`，完整命令见[维护工具](tools/README.md)。文档按主题查阅[文档导航](docs/README.md)，验证与预览脚本见[评估目录](evals/README.md)。

运行检查前先安装依赖。更改 React 源码或 Vite 配置时先执行 `npm --prefix frontend run build`，再执行 `python tools/project.py build` 更新静态资源。

```sh
python -m pytest backend/tests evals/test_native_home_gateway.py -q
python tools/verify_ui.py
npm --prefix frontend run typecheck
npm --prefix frontend test
```

- 原生前端源代码：[ui/README.md](ui/README.md)。模板、逐页逻辑、公共模块、样式与路由登记表在ui/。
- 前端生成：`python tools/build_ui.py`；统一验证：`python tools/verify_ui.py`。
- 根目录 HTML 和 assets/ 为构建产物。页面、路由和导航统一在 ui/ 维护，执行构建后更新。
- 小青与文字练习室采用React/TypeScript＋Vite，源码在frontend/assistant和frontend/studio。首次在frontend运行npm ci；修改后npm run build，再运行根目录构建。npm run dev开启热更新；已附编译产物可直接启动同源服务。
- FastAPI业务在backend/app/；frontend/使用Vite维护React页面，app/保留Next历史兼容入口。

| 目录 | 内容 |
| --- | --- |
| ui/ | 当前页面、交互、共享模块、样式与路由清单 |
| backend/app/、backend/tests/ | 服务端与业务回归 |
| frontend/ | React＋TypeScript＋Vite正式交互源码，以及Next历史兼容页面 |
| data/ | 运行题库、候选题、技能树与检索资产 |
| tools/、evals/ | 日常维护命令、评估和预览工具 |
| docs/ | 功能说明、开发日志、证据、版本交付与设计参考 |
| 根HTML、assets/ | 构建生成的原生前端交付产物 |

## 本机预览

也可直接由后端提供当前原生页面、API与WebSocket，不需要启动Next兼容服务：

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 http://localhost:8000/。此入口使用后端配置的数据库；首次启动按backend/.env.example配置，并提前备份已有数据。公开部署还需配置HTTPS、可信反向代理和部署安全措施。

项目现有Python环境为`.\backend\.venv\Scripts\python.exe`。使用当前已配置的语音服务启动隔离预览：

```powershell
.\backend\.venv\Scripts\python.exe tools/build_ui.py
.\backend\.venv\Scripts\python.exe evals/native_home_preview.py --preview-minutes 240 --seed-notes --seed-history-states --voice-provider doubao --local-mail
```

打开http://localhost:3000/。此脚本复用已有Next构建并使用独立演示数据库；生产部署需配置同源HTTP/WS代理。真实语音仅在显式开始或上传样本后调用。纯离线检查改用`--voice-provider dummy`，替身不支持实时对话，也不验证识别效果。

默认预览使用临时数据库。需要在预览重启后保留账户与练习时，可加 `--persist`，数据保存在 `backend/preview-data.sqlite3`。持久化预览从空账户开始，不支持 `--seed-notes`、`--seed-history-states` 等演示种子参数。预览库与开发库相互独立，备份方法见[维护工具](tools/README.md)。

首页现在可直接选择PDF简历并开始练习；工作区提供首页入口，登录后返回原页面。记录轮播先展示三张练习指南，再按当前账户实际数据更新。

账户支持图形验证码注册、确认密码、密码显隐、昵称、头像、邮箱绑定与修改密码。`--local-mail`启动仅监听本机的测试SMTP与[测试收件箱](http://localhost:8025/)，验证码不会发往外部邮箱。正式SMTP与多进程验证码密钥配置见backend/.env.example；本轮未修改真实邮件凭据。

现有凭据仅保存在backend/.env，不打印、不复制到前端、日志、URL或交付包。

GitHub源码不包含本机配置、数据库、验收截图、历史运行日志和本地交付ZIP。docs/logs、docs/deliveries与设计参考中的本机资料可在原工作区查阅；首次克隆后按tools/README.md配置环境并生成产物。

## 当前资料

- [最新项目状态](docs/项目开发进度.md)
- [前端审查与重构报告](docs/前端审查与重构报告-2026-10-30.md)
- [题库维护](docs/题库审校与发布说明.md)
- [语音接入](docs/豆包语音接入说明.md)
- [本次以前的README历史](docs/archive/README-before-frontend-refactor-2026-10-30.md)

单次本机检查、离线替身和作者示例不能当作语义质量、真实麦克风、生产容量或跨浏览器验收。各批次证据以时间和当前代码为准。

登录后进入个人空间，查看练习统计、继续未结束场次、回看最近报告和安排复习；资料与安全设置按需展开。语音页面支持麦克风选择、授权与设备错误提示，以及录音文件替代入口。

账户安全页可查看有效会话数量并验证密码后退出其他会话。数据库启动采用版本登记与事务锁，维护命令及备份恢复说明见[数据库版本与运维](docs/数据库版本与运维.md)。最新修改及验收边界见[重构日志](docs/archive/development/开发日志-2026-11-02-数据可靠性与会话管理重构.md)。

头像支持本地裁剪、拖动缩放和128/256/512像素尺寸选择；账户支持已绑定邮箱找回密码与验证后更换邮箱，密码重置会撤销旧登录。详见[头像裁剪与邮箱恢复](docs/archive/development/开发日志-2026-11-02-头像裁剪与邮箱恢复.md)。

我的题单支持当前页多选、批量收藏、标记已看过/待回看和确认后批量移除。批次统一校验归属、版本与容量，遇到冲突整批不修改；重复收藏保留原状态。详见[题单批量整理](docs/archive/development/开发日志-2026-11-02-题单批量整理.md)。

最新维护：[项目文件整理](docs/archive/development/开发日志-2026-10-30-项目文件整理.md)。最近功能：[语音检查与账户体验优化](docs/archive/development/开发日志-2026-10-30-语音检查与账户体验优化.md)。
