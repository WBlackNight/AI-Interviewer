# 青栈原生前端源代码

这里是当前21页前端的模板与样式维护入口。根目录HTML与assets/中的CSS、JS是交付产物；业务页面HTML、CSS、页面JS、共享账户菜单JS和桌宠启动JS共五个初始静态请求，后台页面不加载桌宠，共四个。业务API另计，悬浮聊天包在用户展开时加载。

- manifest.json：页面、地址、脚本、工作区导航和样式顺序的唯一登记表，本机网关也读取它。
- templates/：完整页面模板。公共工作区导航用标记生成；练习、报告及语音保留场景内导航。
- modules/home/：首页按导航、演示、动效、评分示例、配置与轮播拆分，构建时组装。
- pages/：每页业务状态机与事件。不要将正式评分状态混入实时陪练。
- shared/：会话校验、文本DOM构造、匿名/账户令牌、JSON响应身份保护，以显式include标记注入各自IIFE；account-menu.js与qing-pet.js单独生成公共脚本，避免跨页重复逻辑。
- styles/：按manifest顺序合并，基础、组件、首页、工作区、控件、阅读层级、布局与导航分开维护。顺序是级联合约；新增组件在对应模块修改，避免再向交付文件追加覆盖。

在项目根目录运行：

```powershell
.\backend\.venv\Scripts\python.exe tools/build_ui.py
.\backend\.venv\Scripts\python.exe tools/build_ui.py --check
.\backend\.venv\Scripts\python.exe tools/verify_ui.py
```

生成器只依赖Python标准库，先验证所有文件和manifest中每页显式JS字节上限，再写交付文件。原生脚本保留函数名、语句换行与源代码可读性，交付缩进使用制表符并删除整行注释；React入口复用Vite编译包，并核对源码哈希。--check不写文件，用于CI拒绝源代码/交付不同步。

首页现含首屏三步可访问切换与滚入视口时的0递增计数，支持减少动态效果；两个演示tab组分别作用于自己的面板。首页新增共享目录与大纲预览，manifest显式预算34KB；账户页46KB、实时对话24.5KB、报告页24KB、语音和题单22KB、文字练习和计划页17KB，其他页面默认15KB。题单增加批量收藏与整理，batchselect.js只注入题单，不增加运行时请求。新增公共菜单脚本，不增加框架依赖。13个顶层样式模块按序合并；工作区大文件进一步按12个业务域拆分，组装顺序在30-workspace.css。

账户结构统一检查token、账户ID、用户名和有效期。HTTP公共层在JSON正文读取完成后再次核对会话；保留每页的取消、请求期限与错误恢复，不重试写操作。报告二进制导出及WebSocket仍使用各自的令牌复核与清理逻辑。

默认预览是离线隔离数据；只有显式启用真实服务才会联系供应商。前端、源代码、交付包均不能包含backend/.env或其密钥。

microphone.js以include注入两种语音页，统一设备选择、授权超时及迟到流释放；枚举设备不申请权限，只有用户点击开始才调用getUserMedia。语音页新增输入支持与失败恢复，预算显式调整为22KB。选择控件保留原生语义，桌面支持base-select的浏览器增强下拉面板，移动端及旧浏览器保留原生选择。

首页轮播默认展示三张固定练习指南，登录且有已作答记录时替换为账户摘要；无记录、退出或请求失败回到指南，指标只来自当前账户dashboard。支持键盘切换、暂停和减少动态效果。登录回跳仅允许同源应用页面，首页PDF仅在提交时上传。语音自动判停事件会先停止采集并等待保存；两种语音页允许30秒有界播放缓存。大功能页预算单独声明，其余页面仍默认15KB，不能隐式放宽。

动效时长和缓动统一定义在 `00-tokens-base.css`。按压反馈使用 100ms，控件状态使用 160ms，内容切换使用 240ms，首页首屏使用 360ms。通用入场只改变透明度和位置，键盘焦点立即可见。开启系统的减少动态效果后，样式层停用动画和过渡，首页数字直接显示最终值，轮播保留手动切换。

岗位展示数据由 data/roles.json 与运行题库生成，构建器与服务端共享 backend/app/practice_policy.py。练习方向页为 /roles，首页新请求仅提交岗位、主题、强度和预计用时来预览安排。practicepreview.js 不提交简历文本和账户凭据，错误时保留用户配置。

CSS 与脚本地址附带构建时的内容摘要版本号，生成器在资源内容改变时自动刷新引用地址。统一前端检查同时验证摘要与实际文件一致。

工作区导航显示常用入口，其余按我的准备、记录与复盘、账户与帮助分组。原生details保留键盘操作，公共navigation.js统一处理互斥、点击外部及Escape关闭。

配置地址只允许岗位、强度、模式、时长和有效主题。刷新及前进后退可恢复配置；复制链接不携带简历和账户数据。新请求使用shared/http.js统一超时、取消和登录身份复核，写请求不自动重试。

顶部导航统一从manifest生成，常用入口与更多功能分组在首页和工作区保持一致。首页预填演示每4.8秒自动切换，在隐藏、离开视口、悬停、聚焦或减少动态效果时暂停。notice.js发送显式操作结果，feedback.js显示约2秒的成功或失败轻提示；详细表单错误保留。历史记录页预算16KB。

小青页面在/assistant，组件源文件在frontend/assistant。先用npm run build生成ui/compiled，再运行Python构建。编译结果有源码哈希校验。助手页和文字练习页各自加载React；其他页面仅在点击桌宠后加载qing-widget.js。四个入口各有190KB脚本预算，包含React生产运行时。

文字练习室现已迁移至frontend/studio，页面脚本由Vite生成，预算190KB；正式源码与小青统一使用npm run build。独立样式为98-react-practice.css，输出practice.css。旧原生练习脚本与DOM替身测试已由TypeScript状态测试替换。

跨页桌宠由shared/qing-pet.js与petposition.js维护，聊天窗组件在frontend/widget，动效与布局在styles/99-qing-pet.css。账户头像弹窗由modules/account/avatar.js、templates/account.html和styles/91-avatar-dialog.css维护；图片仅在确认后上传，沿用服务端格式、尺寸及身份校验。当前账户页脚本预算46KB。完整交互与验收见docs/小青桌宠与头像弹窗-2026-11-17.md。
