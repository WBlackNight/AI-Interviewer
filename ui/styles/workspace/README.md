# 工作区样式

原 30-workspace.css 按既有业务边界拆分为 12 个源文件。30-workspace.css 保留组装顺序，构建器读取 `@style workspace/name` 并合并到 assets/home.css。

此目录按基础、复习任务、语音、日程、账户、报告、文字练习、概览、题库、题单、覆盖与准备计划划分。拆分不改变原级联顺序，不使用运行时 CSS import。

新增组件请修改所属文件；全局色彩和动效变量在 00-tokens-base.css；导航在 70-workspace-shell.css；新练习入口与主题推荐在 85-practice-experience.css。不要直接编辑 assets/home.css。
