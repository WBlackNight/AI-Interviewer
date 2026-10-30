# AI Interviewer · 青栈 QINGZHAN

AI模拟面试与复习工作区，支持文字与语音作答、逐轮报告、准备计划和复习笔记；运行题库120题，Java、Python、市场营销、运营管理、教育教学与英语面试六个方向各20题。

## 开发入口

日常操作统一使用`python tools/project.py`，完整命令见[维护工具](tools/README.md)。文档按主题查阅[文档导航](docs/README.md)，验证与预览脚本见[评估目录](evals/README.md)。

- 原生前端源代码：[ui/README.md](ui/README.md)。模板、逐页逻辑、公共模块、样式与路由登记表在ui/。
- 前端生成：`python tools/build_ui.py`；统一验证：`python tools/verify_ui.py`。
- 根目录16个HTML和assets/为生成后的交付文件，不直接追加覆盖。每页加载一个CSS、页面JS和共享账户菜单JS。
- FastAPI业务在backend/app/；既有frontend/保留Next兼容入口，不是本轮原生UI的编辑入口。

| 目录 | 内容 |
| --- | --- |
| ui/ | 当前页面、交互、共享模块、样式与路由清单 |
| backend/app/、backend/tests/ | 服务端与业务回归 |
| frontend/ | Next兼容工程及本机预览依赖 |
| data/ | 运行题库、候选题、技能树与检索资产 |
| tools/、evals/ | 日常维护命令、评估和预览工具 |
| docs/ | 功能说明、开发日志、证据、版本交付与设计参考 |
| 根HTML、assets/ | 构建生成的原生前端交付产物 |

## 本机预览

项目现有Python环境为`.\backend\.venv\Scripts\python.exe`。使用当前已配置的语音服务启动隔离预览：

```powershell
.\backend\.venv\Scripts\python.exe tools/build_ui.py
.\backend\.venv\Scripts\python.exe evals/native_home_preview.py --preview-minutes 240 --seed-notes --seed-history-states --voice-provider doubao --local-mail
```

打开http://localhost:3000/。此脚本复用已有Next构建并使用独立演示数据库；生产部署需配置同源HTTP/WS代理。真实语音仅在显式开始或上传样本后调用。纯离线检查改用`--voice-provider dummy`，替身不支持实时对话，也不验证识别效果。

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

登录后进入个人空间，查看练习统计、继续未结束场次、回看最近报告和安排复习；资料与安全设置按需展开。语音页面支持麦克风选择、输入电平、授权与设备错误提示，以及录音文件替代入口。

最新维护：[项目文件整理](docs/开发日志-2026-10-30-项目文件整理.md)。最近功能：[语音检查与账户体验优化](docs/开发日志-2026-10-30-语音检查与账户体验优化.md)。
