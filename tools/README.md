# 项目维护工具

在根目录使用项目Python环境执行，命令不自动安装依赖，不修改backend/.env。

| 命令 | 用途 |
| --- | --- |
| `python tools/project.py status` | 检查Python、Node、配置文件与已有Next构建是否存在；不读取配置值、不代表服务在线 |
| `python tools/project.py build` | 从ui/生成根HTML与assets/ |
| `python tools/project.py check` | 校验生成漂移与原生前端；可追加`--json-out 路径` |
| `python tools/project.py preview --voice-provider doubao --local-mail` | 启动隔离预览与本机测试邮件；复用现有Next构建 |
| `python tools/project.py package` | 更新三个原生前端ZIP，先检查漂移与凭据，再逐成员核对字节 |
| `python tools/test_project.py` | 打包边界回归 |

Windows推荐将上面的python替换为`.\backend\.venv\Scripts\python.exe`。后端回归单独运行`python -m pytest backend/tests -q`；测试邮件与网络检查需要本机端口可访问。

首次配置环境时，用Python 3.12创建backend/.venv，安装backend/requirements.txt；仅在没有backend/.env时参考.env.example创建本机配置。预览还需要在frontend/运行npm ci与npm run build生成兼容构建。已有环境直接使用status检查，无需重复安装或覆盖配置。

build_ui.py和verify_ui.py继续作为兼容入口。根目录的HTML是必要交付产物，不要手动移走；修改ui/后重新构建。package只维护前端包，不覆盖题库版本包，不包含后端、数据库、配置或用户上传文件。ZIP时间戳固定，同一份源码在相同Python环境下重复打包得到相同字节。
