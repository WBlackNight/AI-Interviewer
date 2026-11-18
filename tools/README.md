# 项目维护工具

在根目录使用项目Python环境执行，命令不自动安装依赖，不修改backend/.env。

| 命令 | 用途 |
| --- | --- |
| `python tools/project.py status` | 检查Python、Node、配置文件与已有Next构建是否存在；不读取配置值、不代表服务在线 |
| `python tools/project.py build` | 从ui/生成根HTML与assets/ |
| `python tools/project.py check` | 校验生成漂移与原生前端；可追加`--json-out 路径` |
| `python tools/project.py preview --voice-provider doubao --local-mail` | 启动隔离预览与本机测试邮件；复用现有Next构建 |
| `python tools/project.py package` | 更新三个原生前端ZIP，先检查漂移与凭据，再逐成员核对字节 |
| `python tools/package_source.py` | 生成完整开发源码ZIP及SHA-256，包含后端、题库、测试和配置模板，排除本机私有数据与依赖缓存 |
| `python tools/test_project.py` | 打包边界回归 |
| `node tools/build_frontend.mjs` | 用Vite编译小青、文字练习室、悬浮聊天与后台工作台；先在frontend运行npm ci及npm run typecheck |
| `python evals/assistant_quality.py` | 离线核对已知知识错误回归样例，不调用外部模型 |
| `python evals/assistant_probe.py` | 公开合成题目探针；只有加--live才调用已配置模型 |

Windows推荐将上面的python替换为`.\backend\.venv\Scripts\python.exe`。后端回归单独运行`python -m pytest backend/tests -q`；测试邮件与网络检查需要本机端口可访问。

首次配置环境时，用Python 3.12创建backend/.venv，安装backend/requirements.txt；仅在没有backend/.env时参考.env.example创建本机配置。修改React页面时在frontend运行npm ci（首次）和npm run build，再生成同源UI。已有预编译结果可直接启动。已有环境直接使用status检查，无需重复安装或覆盖配置。

统一同源启动使用 python tools/project.py serve --port 3000。独立离线数据库可用 python tools/project.py serve --offline --database backend/demo.sqlite3。启动器固定后端工作目录，--database 相对于调用者目录解析。模块职责和迁移步骤见[代码结构与迁移指南](../docs/代码结构与迁移指南.md)，升级命令见[数据库版本与运维](../docs/数据库版本与运维.md)。

build_ui.py和verify_ui.py继续作为兼容入口。根目录HTML为运行所需的交付产物，修改ui/后重新构建。package生成原生首页、工作区和前端源码三个ZIP。完整服务端交付单独打包。ZIP时间戳固定，同一份源码在相同Python环境下重复打包得到相同字节。

源代码包同时包含标准库实现的共享岗位规则与公开题库数据，便于在新目录重新生成相同前端。构建会为 CSS 和脚本添加内容版本号，部署时一起更新 HTML 与 assets。

SQLite数据备份：先确认实际数据库路径，再运行 `python tools/backup_database.py backend/dev.db backups/青栈-备份.sqlite3`（需先创建目标目录）。工具使用SQLite在线备份并执行完整性检查，目标文件必须不存在。备份包含账户和练习等私有数据，应妥善保管。恢复前先停止服务、另存当前库并验证备份；此工具不自动覆盖或恢复数据库。预览使用隔离临时库，和backend/dev.db是不同的数据源。

可选择 `python tools/project.py preview --persist --local-mail --voice-provider doubao` 使用独立的backend/preview-data.sqlite3；默认仍使用临时库。持久化模式从空账户开始，不写入演示种子，也不允许传入种子参数。要备份该库，将备份命令源路径改为backend/preview-data.sqlite3。
