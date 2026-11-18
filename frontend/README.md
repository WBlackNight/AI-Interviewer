# 青栈 React 前端

正式交互页面使用React＋TypeScript＋Vite。assistant/维护小青及共享对话状态，studio/维护文字练习室，widget/维护跨页悬浮聊天窗，admin/维护后台工作台，shared/维护共用组件，lib/保留账户访问及协议类型。app/与components/是历史Next兼容页面，使用legacy命令，未作为本次运行入口。

首次npm ci；npm run dev开启Vite热更新（后端127.0.0.1:8000），npm run build执行严格类型检查并构建四个生产入口；npm test验证传输、账户、管理台与练习状态。随后从项目根目录运行python tools/project.py build和serve。npm start也可通过本机backend/.venv启动同一服务，默认3000端口。

编译结果在ui/compiled，带源码哈希，普通同源启动不要求安装Node。页面布局在ui/templates，React页面独立样式在ui/styles/97-assistant.css、98-react-practice.css，悬浮助手样式在99-qing-pet.css，公共导航由ui/manifest.json维护。修改共享源码后需重建全部React入口。小青桌宠仅在用户展开时加载React聊天包；跨页恢复仅记录当前账户的会话ID，正文从服务端读取。

dev:legacy与build:legacy保留Next兼容命令。当前生产构建和验收范围详见docs/技术栈迁移与优先级执行-2026-11-16.md。

后台入口为/admin，独立样式为ui/styles/100-admin.css。服务端ADMIN_ACCOUNT_IDS配置管理员，ADMIN_VIEWER_ACCOUNT_IDS配置只读观察员。业务摘要不含简历和回答正文；管理员可导出、保存版本化题库审校并查询操作记录。接入与改进清单见docs/后台差距评估与优先级执行-2026-11-17.md。
