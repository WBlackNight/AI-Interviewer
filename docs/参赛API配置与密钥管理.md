# 参赛 API 配置与密钥管理

## 使用哪种环境

| 环境 | 配置入口 | 评审体验 |
| --- | --- | --- |
| 本地离线 | `tools/project.py serve --offline` | 题库、账户、社区、文字面试、报告、本地规则助手 |
| 本地真实服务联调 | 从 `backend/.env.example` 新建 `backend/.env`，普通启动 | 由后端按需启用模型、语音、远程嵌入、判题或邮件 |
| 云端演示 | 从 `deploy/cloud/app.env.example` 初始化 `deploy/cloud/app.env`，站点参数在 `deploy/cloud/.env` | 浏览器只连接站点，服务端持有供应商凭据 |

从仓库根目录运行下列命令可使用隔离数据库完成文字流程。将 `python` 替换为已安装项目依赖的虚拟环境解释器。

```sh
python tools/project.py serve --offline --port 3000 --database backend/competition-demo.sqlite3
```

保持日常数据库和真实云端数据路径独立。已配置的本地 `.env` 由启动器在 `backend/` 工作目录读取。

## 环境变量

| 服务 | 参数 | 使用方式 |
| --- | --- | --- |
| 文本 LLM | `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` | 同一供应商的 API 地址、具体模型名与密钥。未配密钥时显示本地规则或题库指引 |
| 语音 | `VOICE_ENABLED=true`、`VOICE_ASR_PROVIDER=doubao`、`VOICE_TTS_PROVIDER=doubao`、`DOUBAO_VOICE_API_KEY` | 语音凭据与文本独立。云端可用 `tools/cloud_setup.py --voice` 在隐藏输入中填写；旧版应用按部署指南配置 |
| 检索 | `RETRIEVAL_PROVIDER`、`EMBEDDING_PROVIDER`、`RETRIEVAL_INDEX_PATH`、`EMBEDDING_API_KEY` | 默认 BM25 和 hash 可离线。远程嵌入需启用对应提供方，并用匹配的模型、维度和索引 |
| 可选判题 | `JUDGE0_URL`、`JUDGE0_API_KEY` | 仅在配置后启用外部判题。服务地址及访问凭据放后端 |
| 账号邮件 | `MAIL_MODE`、`SMTP_HOST`、`SMTP_PORT`、`SMTP_SECURITY`、`SMTP_USERNAME`、`SMTP_PASSWORD` | 线上使用已配置的 TLS SMTP。默认关闭发信 |
| 会话与管理 | `AUTH_CHALLENGE_SECRET`、`ADMIN_ACCOUNT_IDS`、`ADMIN_VIEWER_ACCOUNT_IDS` | 云端初始化在服务器生成验证码签名密钥。管理权限根据账号 ID 显式授予 |

前端模板 `frontend/.env.example` 仅定义代理端口、兼容入口和公开开关。任何会被打入浏览器包的环境变量都按公开值处理。

## 验证顺序与故障定位

1. 访问站点的 `/api/health`，检查服务状态、题库数和启用项。线上 Caddy 不公开 `/docs`、`/openapi.json` 或诊断端点，接口说明可在本地打开。
2. 检查 `/api/voice/config`。能力开关有效后，继续用真实设备走查麦克风权限、识别、播放与完成状态。使用明文公网地址时，浏览器麦克风通常不可用，按部署说明启用 HTTPS。
3. 文本或语音返回 401/403 时，先区分站点登录/资源权限和供应商鉴权。应用权限通过重新登录或正确的资源归属处理，供应商鉴权在服务器核对变量、模型权限与额度。
4. 遇到 429 或流式中断时，核对应用限流和供应商额度。文本练习可用离线模式复现。语音替身可查协议，真实识别与播放在正式环境单独测试。
5. 检查页面与接口是否属于同一版本。社区页面及公开列表可分别通过 `/forum` 和 `/api/forum/posts` 确认。

## 发布前检查

- 保留环境模板和依赖锁。公开材料中只列变量名、接口路径和脱敏测试结果。检查 Git 已跟踪文件、历史和生成后的前端静态资源。
- 将供应商密钥、邮件凭据、验证码签名密钥、部署环境文件和数据库留在受控环境。不要通过聊天、命令行参数、URL、截图、视频或公开仓库提交真实值。
- 若确认某项凭据曾公开，先在供应商处撤销并轮换，再按实际泄露范围处理历史和制品。删除当前文件无法撤销旧值。
- 评审账号通过赛事允许的独立字段提供，使用专用测试账户和合成数据。已录制的视频和现有公网演示按原材料提交。

详见 [云部署与语音启用](../deploy/cloud/README.md) 和 [技术文档](参赛技术文档.md)。
