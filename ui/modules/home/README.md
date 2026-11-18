# 首页模块

`ui/pages/home.js` 只负责依赖声明和初始化顺序。这里的文件通过 `@module home/name` 在构建时注入同一个 IIFE，不增加 HTTP 请求，也不创建全局状态。

- navigation：首屏导航、移动菜单与工作区链接。
- demonstration：两个独立演示的 tab 与键盘操作。
- motion：计数与视口入场，处理减少动态效果。
- evidence：示例回答与评分维度联动。
- practice：配置表单、简历提交与创建状态；公开配置由 shared/practiceintent.js 解析。
- carousel：固定指南与账户记录轮播，处理账户切换、可见性和焦点暂停。

首页、方向页、概览和安排预览的新 JSON 请求使用 shared/http.js；历史功能仍可使用 shared/fetch.js 的响应身份保护。WebSocket 和音频流继续由各自状态机管理。

模块依赖 `select`、`selectAll` 等页面词法变量，不能作为独立脚本挂载。新增模块需显式登记在 home.js，并保持 build/check 通过。账户或简历内容不得加入 URL 配置或浏览器持久缓存。
