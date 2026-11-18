# 云服务器部署与语音启用

本包包含当前前后端源码、编译后的页面、题库、测试及云部署文件，可解压继续开发。以下按 **Ubuntu 24.04 + Docker + Compose 2.30及以上** 操作。服务器运行时不需要Node或GPU，修改React源码后才需Node 24构建。

## 1. 只有公网IP也可先验收

公网HTTP页面无法正常申请麦克风，需要浏览器信任的HTTPS。初始化脚本使用 `qingzhan.你的IP用横线连接.sslip.io` 测试域名，自动解析到嵌入的公网IP，无需购买域名；Caddy负责申请与续期HTTPS证书，语音自动使用WSS。例如IP为 `8.8.8.8` 时域名为 `qingzhan.8-8-8-8.sslip.io`，**这个示例不是你的服务器，操作时必须替换**。

测试域名依赖第三方DNS、证书签发条件与网络可达性，适合先测试。长期公开使用建议换成自己控制的域名，设置A记录指向服务器，初始化时改用 `--host interview.example.com`。纯IP也可申请短期IP证书，本包没有将它作为默认路径。

依据：[MDN麦克风安全要求](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)、[sslip.io解析说明](https://sslip.io/)、[Caddy自动HTTPS](https://caddyserver.com/docs/automatic-https)、[Let's Encrypt短期IP证书](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability/)。

## 2. 入口和端口

```text
浏览器 HTTPS / WSS :443
       ↓
Caddy（证书、HTTP跳转、WebSocket和SSE代理）
       ↓ 内部网络 HTTP / WS :8000
FastAPI（网页 + /api + /ws，单进程）
       ├─ 数据卷 /srv/state/app.sqlite3
       └─ 出站HTTPS/WSS → 模型和语音服务
```

在云平台安全组和主机防火墙放行 **80/tcp、443/tcp**，保留自己的SSH端口；443/udp为可选HTTP/3。语音用WebSocket传PCM，不需要额外开放音频UDP范围。允许出站DNS和HTTPS/WSS连接证书机构及语音服务。不要开放8000或数据库端口。

前端继续同源调用 `/api` 和 `/ws`，不写死公网IP，也不暴露模型密钥。使用本包的 **compose.cloud.yml**，根目录旧 `docker-compose.yml` 只是本地依赖环境。

## 3. 安装Docker

已有Docker Engine和Compose 2.30+可跳过。以下仅适用于Ubuntu，其他系统参照 [Docker官方安装步骤](https://docs.docker.com/engine/install/)。

```sh
sudo apt update
sudo apt install -y ca-certificates curl unzip python3
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
cat <<EOF | sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker compose version
```

Compose 2.30+支持 `format: raw`，确保密钥中的 `$` 不被插值。[官方环境文件说明](https://docs.docker.com/reference/compose-file/services/#format)

## 4. 上传并初始化

用SFTP上传zip和同名 `.sha256`，或在本机PowerShell执行，替换SSH用户名和公网IP：

```powershell
scp "D:\AI Web Code\docs\deliveries\AI-Interviewer-2026-11-18-competition-source.zip" ssh_user@你的公网IP:~/
scp "D:\AI Web Code\docs\deliveries\AI-Interviewer-2026-11-18-competition-source.zip.sha256" ssh_user@你的公网IP:~/
```

在服务器SSH终端执行：

```sh
cd ~
sha256sum -c AI-Interviewer-2026-11-18-competition-source.zip.sha256
mkdir -p ~/ai-interviewer-release
unzip AI-Interviewer-2026-11-18-competition-source.zip -d ~/ai-interviewer-release
cd ~/ai-interviewer-release/AI-Interviewer
python3 tools/cloud_setup.py --ip "你的实际公网IPv4"
```

脚本打印最终HTTPS地址，仅生成 `deploy/cloud/.env`（站点）及 `deploy/cloud/app.env`（服务端配置），不会改 `backend/.env`。签名密钥自动随机生成；同一域名重复初始化不改变现有密钥。配置文件仅当前用户可读写。换域名时不自动覆盖已有配置，按第8节修改。

可用 `getent ahostsv4 你的测试域名` 检查解析是否为实际IP。80/443已有服务时，需整合现有反向代理，不能重复绑定，也不要停掉无关服务。

## 5. 启用语音和模型API

```sh
python3 tools/cloud_setup.py --voice
```

隐藏输入自己已开通实时语音权限的 **语音服务API Key**。脚本自动设置VOICE_ENABLED=true、VOICE_ASR_PROVIDER=doubao、VOICE_TTS_PROVIDER=doubao及对应语音密钥。语音和文本模型凭据独立，不能直接用文本模型平台的Key替代语音Key；需要服务开通、有效额度和可达的供应商端点。有出口IP白名单时填写云服务器实际出口IP。不要将密钥放到前端、聊天或Git。

已有旧版语音应用可手动编辑 `deploy/cloud/app.env`：使用DOUBAO_VOICE_AUTH_MODE=legacy、同一应用的DOUBAO_VOICE_APP_ID与DOUBAO_VOICE_ACCESS_TOKEN，同时启用三个VOICE开关。不是Secret Key；此后不要用 `--voice` 切回api_key模式。

小青与模型评分如需联网，在同一文件填写自己的LLM_API_KEY、LLM_BASE_URL、LLM_MODEL。不填时文字练习采用本地规则反馈；语音凭据有效时可独立使用语音。默认邮件关闭，邮箱验证码需要另配TLS SMTP，云端不使用本机测试邮箱。

app.env按原样读取：标量密钥不要额外加引号、换行或行尾注释，CORS_ORIGINS保留脚本生成的JSON数组。不要分享 `docker compose config` 完整输出，它可能显示密钥；检查语法使用 `config --quiet`。

## 6. 启动

以下均在项目根目录执行：

```sh
sudo docker compose --env-file deploy/cloud/.env -f compose.cloud.yml config --quiet
sudo docker compose --env-file deploy/cloud/.env -f compose.cloud.yml up -d --build --wait --wait-timeout 180
sudo docker compose --env-file deploy/cloud/.env -f compose.cloud.yml ps
sudo docker compose --env-file deploy/cloud/.env -f compose.cloud.yml logs --tail=80 caddy
```

首次构建需要下载镜像和Python依赖，app健康后Caddy才启动，证书签发还可能需要时间。证书成功后打开脚本打印的 **HTTPS完整地址**，不用加3000或8000端口；HTTP会跳转，浏览器应无证书警告。不要用静态HTTP服务器或文件方式打开HTML，也不要使用 `--offline` 启动云服务。

云端首次为空数据库，需要自行注册。包内没有本机账号、练习资料或密钥；如需迁移旧数据，另用 `tools/backup_database.py` 备份实际库并在停服和验证副本后迁移，源码zip不是数据备份。

已部署过的站点先按第 8 节备份数据库，保留原来的 `deploy/cloud/.env`、`deploy/cloud/app.env` 和 `app_data` 卷。使用新版完整源码执行本节构建命令，服务启动时自动执行论坛迁移 `007_forum`。

容器自动重启且Docker开机启动后，不依赖Codex、SSH窗口或你的电脑保持在线。远程模型和语音仍需服务器持续联网。目前单进程SQLite、全站语音默认并发2、每连接最长120秒，适合先测试，正式多人使用前需评估容量与服务额度。

## 7. 云端验收

在新版站点检查论坛页面与数据接口。将地址换为站点的实际 HTTPS 地址。

```sh
SITE_URL='https://你的测试域名'
curl -fsS "$SITE_URL/forum" | grep -F 'id="forum-content"'
curl -fsS "$SITE_URL/api/forum/posts"
```

论坛列表初始返回 `{"items":[],"next_offset":null}`，首页菜单应能打开「面试社区」。若首页可访问但论坛请求返回 404，检查运行中的容器是否已用新版源码执行构建和更新。

验证公网HTTPS与API，替换实际地址：

```sh
python3 tools/cloud_check.py --url "https://你的测试域名" --require-voice
```

检查不忽略证书错误，也不将配置存在视为识别成功。接着在容器内建立一次真实语音会话，**可能产生供应商费用**：

```sh
sudo docker compose --env-file deploy/cloud/.env -f compose.cloud.yml exec -T app python /srv/app/tools/cloud_check.py --require-voice --real-voice
```

成功应看到 `provider_session_ready: true`。这只验证鉴权和协议建连，不验证用户麦克风、识别质量或播放；工具保留 `end_to_end_verified: false`。

最后在电脑Chrome/Edge和手机系统浏览器实际验证：

1. HTTPS登录后选择方向、进入练习并看到当前题。
2. 语音输入点击开始才授权麦克风；说完整回答，确认转写，提交后刷新仍可查看回答。
3. 新场练习进入实时对话，连续两轮，检查双方字幕、声音、暂停/继续和结束。
4. 离页或结束后麦克风指示消失，重新进入可再次连接；拒绝权限有提示，可改文字或上传录音。
5. 英语方向重复一次；手机需点击开始后才能播放，建议佩戴耳机。

DNS、证书、语音权限、网络和实际设备全部通过，才算云端语音端到端验收。不要用本地模拟协议测试替代。

## 8. 配置、更新与备份

管理员配置使用注册账户的32位ID，填写app.env的ADMIN_ACCOUNT_IDS；只读角色填ADMIN_VIEWER_ACCOUNT_IDS。不要填写用户名或令牌。在服务器仅查询所需用户名的ID（替换命令末尾的用户名）：

```sh
sudo docker compose --env-file deploy/cloud/.env -f compose.cloud.yml exec -T app python -c 'import sys;from sqlalchemy import select;from app.db import SessionLocal;from app.models.entities import Account;db=SessionLocal();print(db.scalar(select(Account.id).where(Account.username==sys.argv[1])) or "账户不存在");db.close()' 你的用户名
```

改API密钥、管理员或语音设置后，**重新创建容器** 才能读取env，单纯restart不够：

```sh
sudo docker compose --env-file deploy/cloud/.env -f compose.cloud.yml up -d --force-recreate app
```

更换域名时同时改 `.env` 的SITE_HOST及app.env的CORS_ORIGINS，再 `up -d --force-recreate app caddy`。更换站点源后浏览器需重新登录。

更新代码前备份，再在新解压目录保留自己的两个配置文件，使用同一Compose项目名（文件已固定ai-interviewer）重建。持久卷保留数据和证书；**不要执行 `down -v`，它会删除这两个关键数据卷。**

一致性备份与完整性检查：

```sh
BACKUP_NAME="app-$(date -u +%Y%m%dT%H%M%SZ).sqlite3"
sudo docker compose --env-file deploy/cloud/.env -f compose.cloud.yml exec -T app python /srv/app/tools/backup_database.py /srv/state/app.sqlite3 "/srv/state/$BACKUP_NAME"
mkdir -p backups
APP_CONTAINER=$(sudo docker compose --env-file deploy/cloud/.env -f compose.cloud.yml ps -q app)
sudo docker cp "$APP_CONTAINER:/srv/state/$BACKUP_NAME" "backups/$BACKUP_NAME"
```

备份含私人资料，应另存到受控位置。本版自动执行缺失的迁移，包含后台审校 006 和论坛 007。恢复前保留现库、停 app 并在新路径验证备份和权限。参见 [数据库运维](../../docs/数据库版本与运维.md)。仅停止并保留数据：

```sh
sudo docker compose --env-file deploy/cloud/.env -f compose.cloud.yml stop
```

## 9. 排障

| 现象 | 处理 |
| --- | --- |
| HTTPS打不开/证书失败 | 查DNS、80/443、安全组与防火墙、端口占用、出站网络和Caddy日志；共享测试域名可能受DNS策略或证书限额影响，可换自有域名 |
| 麦克风无法启用 | 确认最终地址是可信HTTPS、浏览器及系统允许麦克风；避免应用内置浏览器 |
| voice_config_enabled=false | 核对三个VOICE开关和语音密钥，修改后重建app；不能用离线启动模式 |
| 语音401/403 | 核对语音专用Key、鉴权模式、产品开通、额度和云端出口IP白名单 |
| 语音连接超时 | 查服务器到openspeech.bytedance.com:443的DNS/TLS/WebSocket出站网络 |
| WS403 | 核对HTTPS站点、Host、CORS_ORIGINS；登录所属账户，确认练习未结束；保留Origin校验 |
| capacity/语音忙 | 默认同时2条连接，先结束其他会话；提高并发前确认配额与费用。语音费用不计入文本token预算 |
| 502/503 | `ps`检查app健康，查看app日志；检查环境校验、题库和持久卷写权限 |
| 拉镜像/pip失败 | 使用云平台提供的可信网络/镜像源方案，保持HTTPS校验；API Key不放进镜像构建参数 |

## 本包验证边界

部署结构、HTTPS代理头、同源API/WS、配置初始化、麦克风安全上下文及既有语音协议通过本地回归。当前开发机无Docker引擎，也没有目标云服务器会话，未实际执行该公网IP的容器构建、证书签发或麦克风对话；按第6、7节完成实际验收。
