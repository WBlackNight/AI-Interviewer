# 青栈原生首页接入说明

## 2026-10-29 居中与左右平衡

修正底部四组内容被旧五列规则覆盖的问题，桌面四列等宽；900px以下品牌独占一行、三组导航等宽居中。首页区块标题与数据居中，桌面演示/评分/FAQ/配置双栏等宽，首屏产品画面两侧栏均200px；1000px以下同时隐藏两侧栏。内容与表单内部保持自然阅读对齐。1440/900/390/320宽度无横向溢出、容器左右留白差小于1px，静态结构检查通过。见docs/开发日志-2026-10-29-居中布局与左右平衡.md。

## 2026-10-29 题库扩充与答题优化

运行题库现30题（Java17/Python13），首页快照同步。底部链接去掉箭头、统一16px无衬线字体，整理为练习/复盘/我的准备；删除重复入口及开发验收类文案，保留隐私和评分用途说明。

文字页新增“跳过本题”，保留草稿，本轮记0分未作答后推进；后端explicit-skip-v1不调用评分模型。追问沿逐题路径聚焦真实未覆盖锚点，规则评分heuristic-v3修复简短关系说明被当作堆词的问题。部署需同步session/prober/scorer及语音提示词，重启并新建面试；旧资产恢复保护保留。739项后端目录回归及最终156项评分专项通过，数量不相加。详见docs/开发日志-2026-10-29-题库扩充与答题优化.md。home.js/interview.js原始14,821/14,981字节，仍34文件。

## 2026-10-29 语音对话测试与完善

实时陪练增加服务能力检查、异步准备/文件读取取消保护、上传期间结束操作和剩余时间倒计时。未启用实时服务时，开始与文件输入禁用；部署须提供/api/voice/config中的realtime_enabled。当前题仍只读，陪练不自动提交正式评分。

一次真实同连接两轮检测通过，包含当前题上下文发送、自然判停、文字/音频与取消确认；58项后端专项及两套前端离线状态检查通过。浏览器离线验证桌面/手机、同场同题返回和禁用入口。真人麦克风、回声、回答质量及计费尚未验收。详见docs/开发日志-2026-10-29-语音对话测试与完善.md。realtime.js原始14,949字节，工作区仍34文件；本批隔离预览验证后已停止。

## 2026-10-29 阅读、边距与路由完善

本轮将共享CSS中小于14px的文字声明统一提升至14px，包含响应式与font简写；主要说明、回答正文和输入控件采用16px。等宽字体栈增加本机中文无衬线回退，数字与代码仍优先等宽。手机卡片内边距统一20px，页面上下留白调整，导航、连接状态和操作按钮允许换行，语音控制按钮在手机单列排列。

文字练习新增同场“实时陪练 · 不计分”直达链接。本机网关对已知页面的.html入口及页面/详情尾斜杠返回308规范地址，保留查询参数；详情仍要求合法场次ID，未知路径不回退。正式部署需实施同样的精确映射与规范化规则；ZIP只含原生静态资源，不含网关。

31项网关回归通过；16页在1440/390/320宽度检查无横向溢出、可见文字至少14px，三种模式同场跳转通过。验证使用离线合成数据与dummy语音，未申请麦克风、未调用真实模型。详见docs/开发日志-2026-10-29-阅读边距与路由完善.md。工作区仍34文件，每页三个静态资源，单页JS小于15,000原始字节。

## 2026-10-29 字体排版与当前题陪练

工作区标题/正文统一无衬线本机字体回退栈，品牌标题与等宽数据另行保留；排版规则集中在home.css末尾。realtime.html增加当前题和跟随字幕开关；realtime.js调用只读/api/interview/{id}/realtime-context，并接受WS ready中的question。部署须同步这两个后端变化。75项针对性回归及最终12项实时模块回归通过；详见docs/开发日志-2026-10-29-字体排版与题目陪练.md。

## 2026-10-29 实时语音陪练

新增realtime.html与assets/realtime.js，从正式语音页进入同场?mode=realtime；部署需要该模板路由及/ws/realtime/{id}，后端开启真实豆包语音。该模式为模型自主对话，不自动提交正式评分。UI状态、文字及三静态资源约束保留；工作区现16个HTML、16个JS、共享CSS与本说明，共34文件。配置与检测记录见docs/开发日志-2026-10-29-实时语音陪练.md。以下各节计数为历史批次。

## 2026-10-29 语音体验优化

voice.html增加步骤、状态音球与本段时长；home.css提供桌面双栏、手机单栏和减少动态效果适配。voice.js使用可读制表符缩进，静态文案集中在voice-copy；保留单脚本、三静态资源，不需构建。合成与播放期间锁定朗读，结束后复位；断线释放等待状态以允许同步，文件上传先初始化音频上下文。时长按已发送100ms音频帧统计，非服务器计费用量。验证见docs/开发日志-2026-10-29-语音体验优化.md。

## 2026-10-29 豆包语音联调

当前文字页点击“语音作答”，同一/interview/{id}?mode=voice返回voice.html，单脚本assets/voice.js，仍复用home.css。正式静态/模板路由须实现该查询选择，并为voice.html保留data-ws-base配置；前端不接触语音Key。当前工作区15个HTML、15个JS、CSS和本说明，共32文件。完整配置、协议、CSP、新旧鉴权选择、真实联调与计费边界见docs/豆包语音接入说明.md。

默认语音关闭；--voice-provider dummy预览明确显示离线替身，不能视为识别/音质结果。747项回归通过；旧版APP ID与Access Token已完成真实短WAV识别、保存、追问与手动播报，Secret Key不参与。原12项文字协议及离线报告链路记录保留；音质、真机与计费尚未验收。部署同步后端voice/config/read_question及适配器，前端只替换文件，无Next构建。以下为各历史批次的实现记录。

## 2026-10-28 功能与布局续批

任务板revision-board.js新增今天/明天/一周后快捷日期，使用接口today的北京时间日历加日，只填写草稿，仍需点击保存。日期值不从浏览器本地时区推导；按钮沿用提交锁和离页草稿保护，不增加接口。修改按钮文字在card内，样式在home.css的“任务安排”模块。任务板脚本原始14,870字节，部署需同步revision.html、JS与共享CSS。

plans-toolbar在560px以下改为两列，防止选择框和按钮挤压重叠；plans-themes复选胶囊保持原生键盘操作和3项上限。首页合成规则标签改为heuristic-v2，得分仍为6.3，实际后端需同步评分器代码；旧报告来源保留。713项回归与七页1440/390布局检查通过，详见docs/开发日志-2026-10-28-评分修正与布局巡检.md。以下页面重构数据为前一批记录。

## 2026-10-28 页面重构

首页已改为银白/青绿配色、居中标题和完整练习窗口；结构与演示文案在index.html，新增视觉集中于home.css末尾的“共享视觉/首页/配置选择”模块。参考Apple产品页的内容层次与留白，保持青栈字体与本地SVG，不请求Apple或其他外部资源。

选择框继续使用原生select，统一50px高度、圆角、CSS箭头、键盘焦点、禁用状态与手机16px字号。catalog-builder/library-practice/plans-builder保留深色变量，首页配置改为亮色面板；弹出列表由操作系统或浏览器绘制。单选模式与主题复选使用原生输入配合分段/胶囊样式，接口值及提交逻辑不变；首页hard显示名统一为“挑战”。

home.js的revealSections替代数字计数动画：区块进入视口后显现一次，数字始终显示真实值。product-enter/product-glow/answer-emphasis分别为1.2/3.6/3.8秒且只播一次；prefers-reduced-motion会停止动画、直接显示内容。无脚本或缺少IntersectionObserver时区块保持可见。标题直接显示，动效不等待首屏文字、不劫持滚动。

本次脚本原始14,820字节；首页静态441元素，一体化页面含动态主题与审计组件453元素/867节点，1440与390宽无横向溢出。独立静态版仍为HTML/CSS/JS三项请求，一体化模式另有既有业务API。29网关、12原生协议及浏览器创建专项/计划筛选通过；本机LCP120/156ms、CLS0为单次采样，Safari/真机和正式环境仍需验收。详见docs/开发日志-2026-10-28-首页与控件重构.md。

body的data-api/data-workspace-base接入标记保持原样，一体化网关仍会按原约定注入，不能随意改写该标记。共享CSS影响全部15页，部署应同时替换HTML/CSS/JS并刷新缓存；工作区32文件包已同步。回退原视觉可参考本次日志目录中的before-source.zip。

本页复用`docs/references/design-exploration/preview/v1-mist.html`（原promote of chuanzhibei目录）的雾林视觉，保留窗口、能力索引和流程样式，并根据实际代码重写内容与交互。原三版预览保留。无需安装依赖、执行npm或重新构建Next.js。

## 四个交付文件

```text
index.html
assets/home.css
assets/home.js
assets/README.md
```

将`index.html`和`assets`保持相对位置，放入后端静态目录即可。Spring Boot可放入`src/main/resources/static/`；Thymeleaf/JSP可把HTML放入模板目录、assets放静态目录，并按部署前缀调整两个资源路径。普通静态服务器也能使用。若模板只允许单文件，把home.css放入head中的style、home.js放入body尾部script，并移除对应外链；无需修改交互逻辑。

### 原生复习笔记扩展

原生工作区均复用home.css：voice.html/voice.js为语音练习；plan-history.html/plan-history.js为计划练习记录；`revision-notes.html`/revision-notes.js为笔记，`revision.html`/revision-board.js为任务板，account、history、report、review、interview、dashboard、catalog、library、coverage、plans分别为账户、记录、报告、跨场复盘、文字练习室、练习概览、题库探索、我的题单、题库覆盖、准备计划（同名HTML及assets下JS）。完整三十二文件包见`docs/deliveries/qingzhan-native-workspace.zip`：十五个HTML、十五个JS、共用CSS及本说明；原四文件仍是独立首页包。包内不包含后端服务。

正式部署需将`/notes`、`/revision`、`/account`、`/history`、`/review`、`/dashboard`、`/catalog`、`/library`、`/coverage`、`/plans`、`/plan-history`映射到对应HTML，`/report/{32位小写十六进制id}`及`/interview/{id}`分别映射到report.html和interview.html，保持浏览器地址中的面试ID；不得将任意未知路径都回退为详情。资源统一为`/assets/home.css`和各页单个JS，同源代理`/api`至已有FastAPI。WebSocket的`/ws/interview/{id}`另行代理，见下方说明。`/workspace`的旧配置/PDF入口及`/_next/*`继续使用既有Next服务，HTML不能作为RSC响应解析。本机网关已实现HTTP映射，原Next练习室可经`/legacy-interview/{id}`回看。

笔记页复用sessionStorage的`account:session`，不从URL读取令牌。GET `/api/auth/me`确认登录，GET `/api/account/revision-tasks?limit=10`读取任务；状态/岗位/日期筛选均由服务端执行。GET/PUT `/api/account/revision-tasks/{id}/note`读取/显式保存`{content,expected_version}`，409时保留草稿，用“读取最新版本”比较后手动合并。2,000字按Unicode字符计数；换行规范为LF，保留缩进，只作纯文本显示。草稿只在当前页内存中，不自动上传；页内刷新/筛选/翻页用dialog确认，浏览器离页由beforeunload提醒。

“练习本主题/继续本主题练习”调用既有POST `/api/account/revision-tasks/{id}/practice`，随后进入所属账户的练习室；服务端复用尚未结束的同任务练习。有草稿时先提示处理，创建失败仍保留输入。任务日期和完成状态在原生任务板管理，笔记不更改它们，也不送入模型或报告导出。文字练习室已原生接入；旧配置/PDF入口保留现有构建，独立静态3001首页的工作区链接需要3000服务正在运行。

### 报告与跨场复盘（2026-10-25）

报告页GET `/api/interview/{id}/report`，从当前标签页读取账户会话或该场匿名凭据，统一通过X-Interview-Token访问；账户存在时优先账户，不因403切换身份。按主题、低于weak_score和追问筛选，四轮一页；回答与版本用details展开，能力维度用原生meter。JSON/Markdown导出使用`/report/export?format=...`并保持相同身份，始终包含完整报告；下载对象地址及时回收。未评分显示“—”，进行中和取消分别说明部分报告边界。

POST `/api/interview/{id}/practice`创建薄弱项复练：账户归属返回account_owned且无匿名token，直接沿账户进入练习室；匿名归属须保存新access_token后跳转。POST `/api/account/interviews/{id}/revision-tasks`只通过账户Authorization，重复加入保留进度，匿名报告提示登录并认领。任务专项的revision_source保留原始报告回链；复练不会自动标记任务完成。取消使用原接口和独立确认框，撤回不写入，写操作不自动重试。

跨场复盘GET `/api/account/review`，仅账户模式，每页四场（接口默认仍20），卡片每条为一场的一个主题。展示实际难度、主问题/回答轮数、同版本重复题和来源/版本。岗位、主题、页码写入页面地址并可刷新恢复，绝不写入凭据；未知主题保留为明确的空范围，切换岗位清空主题和页码，失效末页回退。报告中的“同主题跨场复盘”携带当前岗位和所选主题。更换身份后重读，失败重试保留已应用筛选。

两页各自只有HTML/CSS/JS三个静态资源，业务API另计。脚本分别14,931/10,232字节，无新依赖、外部资源或Next构建。文案在HTML和JS的语义文本中，样式在home.css末尾“报告与跨场复盘”模块。验证与边界见`docs/开发日志-2026-10-25-报告与跨场复盘.md`。

### 任务板与内容搜索

任务板每页8项，笔记页每页10项。两页均向GET `/api/account/revision-tasks`提交可选`q`（最多100字符、去首尾空白）和`note_filter=all/with/without`。搜索匹配主题或已保存笔记中的字面子串，英文ASCII大小写不敏感，`%`、`_`、`/`等按普通文字处理；不搜索未保存草稿，不调用模型。不填写关键词或全部空白等同于不过滤。非空保存文本算有笔记，包括保留的空白；清空为空串后算无笔记。

统计counts反映搜索/笔记/岗位范围，date_counts再按所选状态统计，不受当前日期视图和分页影响。所有筛选在显式提交后生效，刷新回默认待复习。搜索词不写入页面URL；授权API的GET参数仍会包含关键词，生产访问日志应按现有脱敏策略处理。新搜索无需表迁移或索引重建。

原生任务板用PATCH `/api/account/revision-tasks/{id}`分别提交`{status}`或`{due_date}`；保存日期、清空、完成与恢复不捆绑其他字段。日期范围、北京时间及原手动语义保持。切换视图、修改其他项或进入练习前，页内dialog保护未保存日期；保存一项不会默默丢弃另一项的日期输入。读取失败保留原卡片，写入超时不自动重试，刷新确认服务端状态。

本轮完整演示（23项任务、两条合成笔记）：

```powershell
.\backend\.venv\Scripts\python.exe evals/native_home_preview.py --preview-minutes 240 --extended-history --seed-notes
```

### 原生账户与练习记录

账户页的登录/注册使用POST `/api/auth/login`和`/api/auth/register`，验证响应后写入原有`account:session`；退出通过POST `/api/auth/logout`只撤销当前会话。账户概览只读记录总数和待复习任务数。账户删除仍需密码和单独确认，沿用DELETE `/api/account`；进行中保护、密码验证和清理规则均由后端执行。密码不进入URL或存储，提交后清空；撤回删除会清空确认密码。

记录页调用GET `/api/account/interviews`，支持可选`position`、`difficulty=easy/mid/hard`、`status=created/running/finished/cancelled`，每页8条，默认后端limit仍20。status_counts对应当前岗位/强度、不受状态与分页影响；positions来自本账户全部记录。旧调用不带筛选时行为和排序保持。筛选只在本页保留，刷新回默认；分页/计数由服务器计算，空末页自动回退。

未登录时只从标签页的`interview:{id}:token`发现最多50条匿名记录，最多四路并发、20秒总读取预算，失败项提示刷新；不会枚举服务器ID。登录后提供逐场认领入口，每组最多5项，认领成功删除原匿名凭据。退出仅清账户会话，保留尚未认领的匿名凭据。取消与永久删除分别弹出确认框，返回记录不发送写请求；不自动重试写入。详情继续使用既有练习室，报告与导出通过原生报告页接入已有接口。

四种状态与筛选完整演示：

```powershell
.\backend\.venv\Scripts\python.exe evals/native_home_preview.py --preview-minutes 240 --extended-history --seed-notes --seed-history-states
```

此模式预置26条合成账户记录（23完成、1进行中、1未开始、1取消）、23项任务与两条笔记。会话、内容和密码均为临时演示数据，到期清理。UI日志与已验证范围见`docs/开发日志-2026-10-24-账户与记录布局.md`。

本机预览：项目根目录执行：

```powershell
.\backend\.venv\Scripts\python.exe -m http.server 3001 --bind 127.0.0.1
```

打开<http://localhost:3001/>。也可直接打开index.html，阅读、菜单、演示、评分与配置预览均不依赖网络。实际面试和账户需要另外启动已有服务。

### 无需重新构建的一体化联调

项目已有`frontend/.next/BUILD_ID`时，可直接复用构建：

```powershell
.\backend\.venv\Scripts\python.exe evals/native_home_preview.py --preview-minutes 240
```

要求3000、3100、8000端口空闲，脚本不会停止其他服务。访问<http://localhost:3000/>即可从原生首页实际创建面试，跳转现有练习室，查看报告和账户历史。脚本在响应时设置接口属性，不改四文件中的离线默认值；3001的纯静态预览可同时保留。

此模式启动独立临时数据库、离线后端及3100端口上的现有Next构建，3000提供同源页面入口。现有构建的API/WS仍访问localhost:8000，所以该后端端口保持固定。页面切换共用sessionStorage，匿名资源与账户凭据均沿用现有契约，不通过URL搬运令牌。

预置演示账户`ui_review_demo` / `local-demo-password-2026`，含3场报告和复习日期任务。仅使用合成数据和规则评分，无外部模型调用。运行时输出stop文件与到期时间；创建stop文件可提前结束，脚本清理自己的进程和临时库。最新运行信息在`docs/logs/2026-10-24/native-home/integrated-preview.json`。到期后演示数据不保留。

已通过浏览器验证匿名Python专项2题8轮、报告、登录认领，以及账户Java文本简历创建、评分、刷新恢复和历史归属。详见[首页接入日志](../docs/开发日志-2026-10-24-首页接入.md)。这是本机联调入口；公网部署需另外核对构建时API地址、HTTPS/WSS与正式反向代理，不使用此Python联调网关承载生产访问。

## 文字练习室与练习概览（2026-10-25）

interview.html/interview.js已接入原文字协议：WebSocket子协议为`['interview', token]`，打开后发送`{type:'start'}`；接收快照后按seq去重回放，按turn_id关联问题、回答和评分。提交携带message_id、turn_id、version、text和可选code；先存入原`interview:{id}:pending`再发送。重连只在相同轮次/版本下重发相同message_id，已提交事件或结束快照清理待保存记录；旧轮内容只读保留，不自动用于新题。未提交草稿仅在本页内存，跨题时保留旧轮内容供回看，不写入客户端持久存储。

默认WS地址使用当前站点ws/wss。正式部署须代理WebSocket升级并配置后端CORS；也可在body的data-ws-base填写明确的WS服务入口，禁止写入凭据。本机HTTP网关不代理升级，仅在响应中把此属性设为`ws://localhost:8000`，因此预览须用localhost:3000访问。连接最多自动重试6次，退避1/2/4/8/10/10秒，授权拒绝停止重连。恢复请求等待上限195秒，覆盖原后端180秒轮次超时；提供显式重新同步入口。

文本按Unicode码点限制20,000字，Python代码按UTF-8限制16KiB。Enter换行，Ctrl/⌘+Enter提交，输入法组合期间不触发提交。提交中锁定输入，ACK后等待新题；已保存轮次四条一页，输入只更新编辑器计数/按钮，不折叠已展开回看。展示上一轮分数及来源，整场综合分仍以报告为准。完整结束和取消分别链接完整/部分报告；取消沿原REST接口并单独确认。语音与真实判题的供应商接入不属于本轮新交付。

dashboard.html/dashboard.js调用新增GET `/api/account/dashboard`，只用账户Authorization，只读本账户四状态总数、待复习/已复习与到期分类、非空笔记项数、近七日已完成场数及少量摘要（未结束3场、最近完成3场、今日/逾期任务4项）。不读取回答、笔记正文或模型。日历按北京时间；既有面试结束时间是宿主本地naive值，边界按相同存储时区转换，不改写旧数据库，部署仍需保持既有存储时区一致。未知完成时间不推定完成日期。

概览的今日/逾期链接为`/revision?status=todo&due=today|overdue`；任务板首次读取只接受白名单状态和日期参数，搜索词和凭据不进入页面地址。首页导航与账户快捷区提供概览入口。两页脚本分别14,997/6,488字节，仍为每页HTML/CSS/JS三个静态资源；业务接口和WS另计。运行`node --test evals/native_interview_test.cjs`验证恢复协议，详见`docs/开发日志-2026-10-25-练习室与概览.md`。

## 题库探索与主题专项（2026-10-26）

新增catalog.html及assets/catalog.js（14,984字节），复用home.css与既有POST `/api/interview`。首页和概览提供入口；手机结果列表后接主题选择区，顶部与列表标题的锚点可以直接跳至主题篮。560宽以下主题单列，避免长名称挤压；没有固定悬浮面板或滚动劫持。

公开GET `/api/catalog`读取当前运行题库，参数为可选position/theme（各1–64字符）、difficulty=easy/mid/hard、kind=all/knowledge/coding、q（最多100字符）、offset（0–1,000,000）、limit（1–24，默认6）。未知岗位404，未知主题返回空范围。q去首尾空白并忽略大小写，字面匹配题干、主题、编号与来源；百分号和下划线没有通配含义。难度严格匹配，不沿用出题阶段的难度放宽。

返回positions及主题数量/可练范围/最多四个子知识点、items、total、offset/limit/has_more、counts和note。题型counts对应主题/难度/关键词范围，先于kind与分页计算。items仅含id/position/theme/difficulty/content/source/is_coding/can_practice，不返回评分锚点、关键词答案或判题用例。接口no-store、不读写业务数据库，不执行召回或LLM/Embedding请求；复用load_assets的现有运行快照及初始化配置，题库文件变更后仍遵循原服务重启/缓存策略。

筛选先选再点“查找题目”；切换岗位与题型直接读取，刷新题库重读已应用条件。公开筛选和页码保存在URL、刷新恢复，主题勾选只在当前页内存，同岗位翻页/筛选保留，换岗位清空。主题上限由服务端返回；仅可用知识根主题可选，编程题只预览。每页六项，空末页回到最后有效页；失败隐藏旧结果并提供重试/清除。

创建请求只传`{position,difficulty,themes}`，其中difficulty来自单独的“练习强度”。专项每主题最多两道主问题、保留追问，按原采样和难度放宽规则出题，不提交预览题ID。已登录沿用account:session/Authorization；匿名保存interview:{id}:token后跳转。创建前检查存储，返回结果校验ID和归属，凭据保存成功后解除提交中离页保护再导航；保存失败可继续同一创建结果，不重复POST。请求超时30秒，提示先查记录，不自动重试写入；当前账户变化会阻止进入旧归属结果。

本批使用短合成队列预览，减少无关场景重复生成：

```powershell
.\backend\.venv\Scripts\python.exe evals/native_home_preview.py --preview-minutes 240 --seed-notes --seed-history-states
```

初始6条账户记录（3完成、1进行中、1未开始、1取消）、3项任务、2项笔记；--extended-history仍可显式开启23场完成报告的长队列。当前运行状态见既有integrated-preview.json指针。新增7项接口行为测试、1项网关测试及catalog_smoke.py，功能接通后统一回归603项；原生协议12项保持。浏览器范围与证据见`docs/开发日志-2026-10-26-题库探索.md`。新页面LCP/CLS与Safari/真机仍需独立验证。

## 我的题单（2026-10-26续）

新增library.html/library.js（14,964字节），共用home.css；题库导航和账户快捷区有入口。题单八项分页，公开题库挑选四项一组；两个区域分别选择岗位，挑选关键词仍按catalog字面匹配。选择后点击对应查找/筛选，刷新页面回到默认范围，不把个人状态写入URL。

所有题单请求都通过当前账户Authorization，GET `/api/auth/me`确认身份。GET/POST `/api/account/question-marks`读取/收藏，POST仅接收`{position,question_id}`；PATCH `/{id}`接收`{status:'todo'|'done',expected_version}`；DELETE `/{id}?expected_version=N`移除。重复收藏不改状态、版本或时间。版本冲突409提示刷新，不自动重试或覆盖；移除必须先确认，撤回不写入。所有个人响应no-store，失效或变化身份隐藏旧内容。

题单新增question_mark表，每账户500条，上线时重启后端由已有create_all补建独立表，不更改既有列。只保存题目身份、手动状态及UTC时间，题干和来源按当前运行资产读取，不保留历史题干副本。题目下架后保留标记并提示不可用，可整理或移除；删除账户会清理收藏。移除收藏不影响题库、练习、报告或复习任务。

可练知识主题卡片沿原POST `/api/interview`创建账户专项，强度来自页面底部独立选择，按主题采样、不锁定收藏题，练习不自动标记已看过。编程题可收藏，但不创建知识专项。创建结果缓存供导航失败后继续，不自动重复POST，超时提示先刷新核对。所有请求有30秒截止，账户会话与资源契约保持。

本批611项后端/网关、12项现有协议测试通过，HTTP/WS验证11题两页、去重、版本冲突、重启后重新登录、完成练习不改变标记及独立清理。浏览器验证10条跨岗位题单、标记/筛选、移除确认撤回、账户退出/重登、直接进入专项与1440/390布局。LCP/CLS及Safari/真机仍未补验，详情见`docs/开发日志-2026-10-26-个人题单.md`。

## 题库覆盖与来源（2026-10-26续）

新增coverage.html/coverage.js（9,031字节），题库页脚链接/coverage。公开GET `/api/catalog/coverage?position=...`按可选岗位读取当前load_assets快照；position限1–64字符，未知岗位404。没有账户或数据库依赖、不执行检索/模型请求，返回no-store。来源登记从当前question_bank_dir/source_registry.json读取并严格校验；缺失/无效时以未登记显示，不影响核心面试和题库文件。

响应包含positions/roles/themes/sources、counts、registry_state和corpus_sha256。知识根主题按easy/mid/hard计数；仅编码主题单独列出，不计知识难度缺口，完全空的技能树根主题计入待补并提示人工确认。未映射主题另计。来源状态仅为登记声明及参考资料核对，不作专家/许可/题目质量验证；当前18题仍标记资料未核对，未将新候选资料状态套到旧题。

岗位和gaps=1进入公开URL，刷新恢复；“仅看待补主题”在当前响应中筛选。难度格链接/catalog并明确kind=knowledge，零题仍为空范围，不使用出题的难度放宽。下载仅导出所选岗位范围的空难度、来源状态、说明与题库摘要，不含题干、答案或个人信息；对象地址及时回收。摘要与索引使用同一题目域口径，不包括来源登记文件，发布记录需另保存该文件摘要。

当前共18题、16知识/2编码、9知识根主题、13个空难度格。六道候选稿放在data/question_candidates，不参与运行加载或覆盖统计。离线维护与下一步发布流程见`docs/题库审校与发布说明.md`；本批620项回归、12项协议、HTTP重启与浏览器导出读回通过。每页仍HTML/CSS/JS三个静态资源，业务API另计，无新依赖或构建。未补验新页面LCP/CLS及Safari/真机。

## 题单衔接、搜索与错误恢复（2026-10-26续）

GET /api/account/question-marks新增可选q（最多100个Unicode字符），去首尾空白、忽略大小写，字面匹配当前题干/主题/题号/来源。百分号、下划线不作通配，岗位内部编号不参与关键词匹配；下架收藏仍可按题号查找。counts跟随岗位及关键词，先于状态过滤/分页，positions仍来自本账户全部收藏；旧请求不带q保持行为。关键词只在页面内存，不写个人筛选URL或浏览器存储。

题库卡片新增“查看或收藏这题”，进入/library?position=...&question=...#library-discover并预填题号，不自动收藏。未登录链接带collect_position/collect_question进入账户页；账户确认后提供返回该题的显式链接。两页只接受白名单岗位/题号，再重建同源路径，不接受任意next URL、不传令牌。普通登录和账户快捷区保持原行为。

题单区与题库挑选区分别读取、分别显示错误。任一失败不隐藏全部工作区，保留可编辑的筛选/查找表单，另一侧仍能使用；失败侧清除旧卡片。超长关键词可直接改正，真实404也可改用默认岗位后重读。会话失效/变化仍隐藏个人内容；读取失败与写入结果不确定分别提示，不自动重试写入。新增清除题单筛选，单条卡片占满当前列表宽度。题单导航增加练习记录，便于核对超时创建结果。

本批覆盖624个回归用例：全量623通过、1项搜索范围失败，修复后题单10项定向复验通过；原生协议12项及隔离HTTP/WS重启冒烟通过。没有重复整套测试或Next构建，截图、初始失败与复验XML均保留在docs/logs/2026-10-26/workspace-refinements/。脚本为题库14,984、题单14,964、账户9,404字节，仍各页单脚本低于15,000。

## 准备计划（2026-10-27）

新增plans.html/plans.js（当前14,994字节），共用home.css，概览导航和账户快捷区提供入口。用户主动保存岗位、知识主题、强度、名称与可选目标日；范围创建后固定，只可编辑名称和日期，归档后可恢复。计划与报告复习任务、题单标记分别保存，不自动评分或提醒；目标日按北京时间日历解释，跨日刷新读取新日历。

GET/POST `/api/account/preparation-plans`读取/新建，PATCH `/{id}`编辑或归档恢复，DELETE `/{id}?expected_version=N`仅移除已归档计划，POST `/{id}/practice`开始/继续。所有个人请求用Authorization且no-store。列表八项分页，岗位与active/archived状态筛选；counts跟随岗位、先于状态/分页，past_target只计准备中且目标日早于今日。完成数为仍存在的所属关联练习中finished场数，删除练习会重算，不是永久累计或能力指标。

POST保存计划只写元数据，不创建面试。名称1–80字，主题上限由/api/positions返回，目标日期可空、范围2000–2100。PATCH和开始请求均带expected_version；编辑范围/强度不受支持，旧版本409。开始时服务端在账户写锁内复用created/running场次；结束或取消后才新建。新场沿原知识专项规则、账户归属与原生练习室接入，不携带计划名称、日期、简历或原回答给模型。

新表preparation_plan/preparation_practice由已有启动create_all补建，无既有列迁移。计划归档不取消练习，移除只清计划与关联，练习/报告保留；删除练习清其关联，删除账户按原进行中保护规则清理全部计划。写入无自动重试，创建超时先查记录，收到练习结果后保留同一结果供进入。新建草稿保留于页面内存；开始已有练习前须先保存或清空新草稿。编辑关闭须确认放弃，冲突保留输入；失效身份隐藏旧内容。

本批635项回归（607后端+28网关）、12项协议与隔离HTTP/WS/重启通过。真实并发4请求只创建1场；浏览器验证新建双岗位计划、改名、草稿保护、归档/恢复、移除撤回、同场继续、日期和退出/重登。桌面1440与手机390均无横向溢出；没有新依赖或Next构建。详情见docs/开发日志-2026-10-27-准备计划.md。

## 通常只需改三处

1. **文案**：修改index.html中标有`EDIT`的区域。标题、副文、FAQ、页脚均为普通HTML。换品牌时同步title、description、logo的aria-label。不要把标签和正文改成JS拼接。
2. **视觉**：修改home.css的`:root`，主要是`--paper`、`--ink`、`--sage-deep`、`--mint`、`--clay`及字体栈。响应式断点为1200、900、560。SVG都是可编辑路径，没有图片或字体下载。
3. **服务入口**：修改index.html的body属性及`data-workspace-path`链接。默认`data-api=""`、`data-workspace-base="http://localhost:3000"`：提交只显示配置预览，不上传简历、不创建面试；工作空间链接指向已有Next.js应用。

### 启用实际创建接口

将首页与现有练习室部署在**同一协议、域名及端口**，首页例如放`/welcome/index.html`，保留现有`/interview/{id}`、`/history`等路由。后端API由同站点反向代理至FastAPI。然后设置：

```html
<body data-api="/api" data-workspace-base="">
```

`data-api`填写API前缀，不包含`/positions`等末段；路径前缀部署需同步调整`data-workspace-base`。启用后按钮变为“开始模拟面试”，且页面会说明输入在点击开始后才提交。默认不会自动启用或探测接口。

home.js中`practiceForm`内的`request`和提交处理集中负责以下契约：

| 接口 | 时机与请求 |
|---|---|
| GET `/api/positions` | 用户点击开始后核对岗位、可用主题和主题上限 |
| POST `/api/resume` | 仅综合面试且文本非空时，发送`{name:"匿名用户",resume_text}` |
| POST `/api/interview` | `{position,difficulty,resume_id?}`；专项改为`{position,difficulty,themes}`，不提交简历 |

请求超时30秒，不自动重试创建。创建成功后验证响应ID/凭据，写入`sessionStorage`中的`resume:{id}:token`或`interview:{id}:token`，再跳转至`/interview/{id}`，兼容现有`frontend/lib/access.ts`。账户会话沿用`account:session`及Authorization；简历使用X-Resume-Token。凭据不放URL、日志或HTML。使用同源是为了保留现有匿名凭据，不能只把跳转链接改成另一个端口就认为接入完成。

本页配置区为精简文字入口，PDF上传继续使用已有练习室，可通过`/workspace`进入原配置页。真实创建已在上述本机隔离模式验证，未在生产服务启用、未调用外部模型。正式部署前仍需验证自身环境中的登录/匿名、简历授权、主题与错误路径。

## 数字与演示内容从哪里来

- 两个岗位、18道题：`data/question_bank/*.jsonl`，Java 11、Python 7，各含1道编码题。它们是示例题数量，不是题库覆盖率或用户规模。
- 岗位与知识主题快照在home.js的`catalog`，需与HTML的岗位option及数据条同步修改。后端实际提交时仍按`/api/positions`校验。
- 三个评分维度来自`backend/app/agent/scorer.py`，没有沿用原稿的五维占位。
- 示例问题为`jv-mysql-index-001`。页面完整示例回答经`HeuristicScorer`实算：总分6.3、技术深度7.5、表达逻辑2.5、岗位匹配6.3；覆盖3/4锚点。表达逻辑的离线估计依据回答长度，不是语义质量评价。雷达按同一比例绘制。
- 对话和追问明确为演示，未声称来自真实用户。没有用户数量、匿名好评、企业背书、15分钟完面或3分钟报告承诺。语音、白板、真实沙箱验证没有作为已交付能力推广。

替换为真实评分时，须同步修改维度按钮、SVG点位、desc文字替代、原文与评分解释；通过textContent写入数据，不拼接不可信HTML。外部模型仅在服务端配置，不将API Key写入这三个前端文件。

## 请求、体积与可访问性

未启用接口时首载只请求HTML、CSS、JS；空data favicon阻止额外favicon请求，字体使用本地回退栈。显式点击“现有练习室”或启用接口后的业务请求不属于首载三请求预算。

保留跳转主要内容、可见焦点、Tab及方向键切换、aria选中状态、原生details与dialog。无脚本时内容可读，配置提交按钮保持禁用。减少动态效果时不做数字动画。默认不上传或缓存简历草稿，刷新后输入消失。

打开`?audit=1`可在DOM的隐藏`#home-audit`输出中查看本机LCP/CLS，输出不上传；不支持相应观察器的浏览器不会生成该项指标。该数字受设备、缓存和网络影响，不等同于移动设备实测或跨浏览器保证。浏览器检查与截图见`docs/开发日志-2026-10-24-原生首页.md`。

本地约束检查（无需构建）：

```powershell
node --check assets/home.js
.\backend\.venv\Scripts\python.exe evals/native_home_check.py
```

## 计划回链与概览接入（2026-10-27续）

更新report.html/report.js、dashboard.html/dashboard.js及plans.html/plans.js，共用现有CSS，无新文件、依赖或构建。三页JS分别14,952/7,620/14,974原始UTF-8字节；工作区仍28文件，每页HTML/CSS/JS三项静态资源，业务接口另计。后端需同时更新preparation与dashboard服务和preparation路由，无新表或列。

报告读取成功后独立GET `/api/account/preparation-plans/source/{interview_id}`，账户Authorization、no-store，返回source=null或id/name/status/target_date当前值。只显示名称和状态，点击返回`/plans?plan_id=...`；失败只影响来源区，可刷新报告重试，报告导出和评分不带计划名称/日期。计划列表GET新增plan_id白名单格式参数，与其他筛选取交集，计数仍先于该定位条件；前端定位时默认全部状态，归档和原分页外计划均可打开。返回全部入口及手动筛选/新建清除定位，草稿保护保持。

GET `/api/account/dashboard`新增preparation对象：counts(active/archived/past_target)、items、limit=3。活动计划按目标日从早到晚，无日期最后，同日按创建时间/id倒序；卡片使用名称/日期与指定计划入口，计数来自全部所属计划。替换文案改dashboard.html及renderPreparation函数，来源说明改report.html；不要把个人名称拼入URL或报告导出。

续批639项回归（611后端+28网关）、12协议通过，原preparation_smoke增加来源、精确定位与概览/重启校验。浏览器与截图、接口边界见docs/开发日志-2026-10-27-计划回链与概览.md。尚未进行真机、Safari或新页面LCP/CLS验证。

## 计划练习记录接入（2026-10-27续）

新增plan-history.html及assets/plan-history.js（8,505原始UTF-8字节），共用home.css；后端静态路由须将/plan-history映射到该HTML，保留plan_id/status/page查询参数。完整工作区现14页、30文件，新增两文件；首页4文件包保持。无新依赖、构建、表或列。

计划卡片新增“计划练习记录”入口，保留继续已有场次与最近报告；plan-history使用账户Authorization GET `/api/account/preparation-plans/{id}/practices?offset=0&limit=8&status=finished`，status可省略。响应plan为当前元数据，status_counts是过滤前的全计划四状态，total为过滤后的总数，items只含摘要与saved_at，不带分数/回答。服务端共同归属检查、no-store，归档可读，移除计划后404而练习保留。需同步部署preparation服务/路由和静态网关，具体契约见docs/计划练习记录设计.md。

文案改plan-history.html与render函数，颜色/双列卡片/手机两列筛选改home.css中的plan-history选择器。JS验证ID/状态/页码，按地址恢复、清筛选回第一页、越界页回有效末页；读取失败隐藏旧数据并重试。时间以Asia/Shanghai显示，saved_at沿用本场归属创建时间。计划页异步读取改为同时校验会话令牌，防止同账户重新登录后旧结果回写。

可选预览：运行原命令时加`--seed-plan-history`，生成10场合成记录（1完成/8取消/1未开始），plan_history_url写入原integrated-preview.json指针。默认不开启；进入最后一场会变为进行中。本批644项后端/网关、12协议和扩展HTTP/WS通过；浏览器验收两页、刷新恢复、筛选、空范围、完整报告、归档继续和1440/390布局。详情见docs/开发日志-2026-10-27-计划练习记录.md。

## 主流程主题复盘接入（2026-10-27续）

不新增页面：plan-history.html新增按需展开的details，plan-history.js当前14,991原始UTF-8字节，共用home.css；工作区仍14页、30文件。后端preparation新增GET `/{plan_id}/review`，只接受所属账户，归档可读；theme可省略、offset 0–1,000,000、limit 1–10默认4。复用原account_review的主问题等权/版本/来源算法，加计划关联和岗位范围；原/account/review公开参数保持不变。需同步部署preparation路由/服务与review服务，无表列迁移。

首次展开才读复盘，主题选择来自本计划已完成评分记录，默认首个排序主题；明确未知主题为空。每主题四场分页，实际难度、来源和同版本重复/未知数可见，证据与详细版本打开原报告。重复口径是本账户全部先前完成记录。模块错误独立恢复，身份失效隐藏个人区；主题选择/页码不写URL，刷新重置。

加入按钮POST `/api/account/interviews/{id}/revision-tasks`，沿用本场完整报告的弱项规则，非“只加入当前主题”。显示added/existing；已有状态/日程/笔记保持，无弱项返回原422，不自动重试写请求。保存中锁定控件及离页保护；离页、会话变化、旧异步返回均有版本校验，避免旧请求清除新操作状态。任务板仍可从已复习任务开始本主题复练，状态不自动改变。

文案改details和renderReview函数，手机布局与单条全宽改home.css的plan-theme-review区域。647回归、12协议及扩展HTTP/WS通过，浏览器验收加入→已复习→重复加入保持→进入复练。证据、启动命令与最新计划ID见docs/开发日志-2026-10-27-主流程闭环.md。后续主要顺序见docs/主流程交付清单.md。
