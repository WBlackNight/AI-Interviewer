# 解压后继续开发

本版包含从云端更新源码包制作的移动端改造。改动清单和实屏验收范围见 [移动端 UX 诊断与交付](docs/移动端UX诊断与交付.md)。

**云服务器与语音：**先阅读 [云部署与语音步骤](deploy/cloud/README.md)。只有公网IP也可生成免费测试域名并配置HTTPS。云端使用compose.cloud.yml，密钥单独填写，不使用下方的离线开发启动命令。

这是当前工作区的完整开发源码快照，包含尚未提交的最新修改。解压后进入 AI-Interviewer 目录操作，请先完整解压，不要直接在压缩包中启动文件。

## 环境与首次启动

推荐 Python 3.12、Node.js 24（用于前端检查和可选 Next 兼容工程）。安装依赖需要网络；安装完成后，可先使用离线模式开发。

Windows PowerShell，在项目根目录运行：

```powershell
py -3.12 -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
.\backend\.venv\Scripts\python.exe tools/project.py build
.\backend\.venv\Scripts\python.exe tools/project.py serve --offline --port 3000
```

Linux / macOS，在项目根目录运行：

```sh
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
backend/.venv/bin/python tools/project.py build
backend/.venv/bin/python tools/project.py serve --offline --port 3000
```

仅在首次使用、没有 backend/.env 时复制模板，保留之后自行填写的配置。浏览器打开 http://localhost:3000/，首次运行会创建空的本地数据库，账户需自行注册。

通过首页菜单「面试社区」或 `/forum` 进入论坛。使用 Vite 开发时，论坛和接口由同源代理传到 Python 后端，端口须和 `QINGZHAN_DEV_PORT` 一致。

离线模式支持页面、账户和文字练习，采用本地规则反馈；实时语音、模型服务与邮件发送需要在 backend/.env 配置自己的服务，并去掉启动命令的 --offline。可在 serve 命令后加 --reload 开启后端开发热重载。

## 修改与检查

- 当前页面源码在 ui/：templates 为模板，pages 为页面逻辑，shared 为公共模块，styles 为样式，manifest.json 登记路由。修改后运行 tools/project.py build，刷新浏览器。
- 小青与文字练习室的React/TypeScript源码在frontend/assistant和frontend/studio。修改后在frontend运行npm run build，再回根目录构建。首次需npm ci；npm run dev提供Vite热更新。已附编译结果和源码哈希，普通启动不需要重新编译React。
- 后端源码在 backend/app/，业务回归在 backend/tests/；题库和岗位定义在 data/。
- 根目录 HTML 与 assets/ 是已包含的生成文件；日常修改请从 ui/ 开始。
- frontend/的正式前端构建现为Vite；app/保留Next历史兼容页面，不用于当前运行入口。兼容命令为npm run dev:legacy和npm run build:legacy。完整网站通过根目录Python同源服务启动，或在frontend执行npm start。
- Windows 使用 .\backend\.venv\Scripts\python.exe tools/project.py check 检查页面构建及交互；需要已安装 Node.js。后端检查使用同一 Python 执行 -m pytest backend/tests -q。

完整职责划分见 [代码结构与迁移指南](docs/代码结构与迁移指南.md)，其余命令见 [tools/README.md](tools/README.md)。

## 包含和排除内容

保留前后端源码、锁定依赖、题库、技能树、配置模板、CI、构建工具、测试和开发文档。SOURCE_MANIFEST.json 记录每个源文件的 SHA-256，便于检查解压文件完整性；它不包含自身。可运行 python tools/package_source.py 重新制作相同类型的完整源码包。

本包不含本机密钥、真实账户及练习数据库、上传资料、虚拟环境、node_modules、构建缓存、运行日志、验收截图、本机参考资料和 Git 历史。可再生检索索引未携带，默认 BM25 不依赖它。需要向量索引时按 data/ 与 evals/ 文档重新生成。

本包用于继续开发，不包含原机器的用户数据。若需迁移已有账户和练习，请通过 tools/backup_database.py 另行备份实际数据库，并按 docs/数据库版本与运维.md 处理；不要把私有数据库当作普通源码分发。

解压后可在根目录运行 git init，创建新的本地版本记录。本机未安装的依赖及第三方服务不会随源码包自动安装或开通。
