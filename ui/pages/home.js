/* 青栈首页：原生DOM，无依赖。 */
(function () {
  'use strict';
/* @include session */
/* @include fetch */

  const select = (selector) => document.querySelector(selector);
  const selectAll = (selector) => Array.from(document.querySelectorAll(selector));
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const catalog = {"education": {"name": "教育教学", "count": 20, "themes": ["教学设计", "沟通与评价", "课堂管理", "教师成长"]}, "english_interview": {"name": "英语面试", "count": 20, "themes": ["Introduction", "Workplace communication", "Career motivation", "Problem solving"]}, "java_backend": {"name": "Java 后端", "count": 20, "themes": ["MySQL", "并发编程", "JVM", "Spring", "Redis", "计算机网络", "Java基础"]}, "marketing": {"name": "市场营销", "count": 20, "themes": ["用户与定位", "活动与评估", "内容与渠道", "品牌与协作"]}, "operations": {"name": "运营管理", "count": 20, "themes": ["流程与协作", "服务与改进", "数据与增长", "项目与风险"]}, "python_backend": {"name": "Python 后端", "count": 20, "themes": ["Python基础", "异步与并发", "Web与数据"]}};

  // 导航：同步菜单状态与吸顶边线。
  function navigation() {
    const header = select('#nav');
    const menu = select('.menu-toggle');
    const links = select('#nav-links');
    let pending = false;
    function toggleMenu(open) {
      menu.setAttribute('aria-expanded', String(open));
      menu.setAttribute('aria-label', open ? '收起导航' : '展开导航');
      links.classList.toggle('is-open', open);
    }
    menu.addEventListener('click', () => toggleMenu(menu.getAttribute('aria-expanded') !== 'true'));
    links.addEventListener('click', (event) => {
      if (event.target.closest('a')) toggleMenu(false);
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && menu.getAttribute('aria-expanded') === 'true') {
        toggleMenu(false);
        menu.focus();
      }
    });
    function updateBorder() {
      pending = false;
      header.classList.toggle('is-stuck', scrollY > 80);
    }
    addEventListener('scroll', () => {
      if (!pending) { pending = true; requestAnimationFrame(updateBorder); }
    }, { passive: true });
    matchMedia('(min-width: 901px)').addEventListener('change', () => toggleMenu(false));
    updateBorder();
  }

  // 演示：点击或方向键切换环节。
  function questionDemo() {
    const tabs = selectAll('.demo-tabs [role="tab"]');
    function activate(index, focus) {
      tabs.forEach((tab, position) => {
        const active = position === index;
        tab.setAttribute('aria-selected', String(active));
        tab.tabIndex = active ? 0 : -1;
        document.getElementById(tab.getAttribute('aria-controls')).hidden = !active;
      });
      if (focus) tabs[index].focus();
    }
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => activate(index, false));
      tab.addEventListener('keydown', (event) => {
        let next = index;
        if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
        else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
        else if (event.key === 'Home') next = 0;
        else if (event.key === 'End') next = tabs.length - 1;
        else return;
        event.preventDefault();
        activate(next, true);
      });
    });
  }

  function heroDemo() {
    const tabs = selectAll('[data-hero-step]');
    const insights = [
      ['从“知道”，到说得有依据。','连接数据结构与查询成本，让思路再往前一步。','范围查询','解释原因与边界'],
      ['沿着遗漏，再问深一点。','从回答里尚未展开的部分，找到下一层追问。','磁盘 IO 与树高度','补上结论背后的原因'],
      ['把复盘，变成下一步。','回看回答和评分要点，把薄弱主题留给下一次练习。','已覆盖 3 / 4 要点','安排一次主题复习']
    ];
    function activate(index, focus) {
      tabs.forEach((tab,n) => {
        tab.setAttribute('aria-selected',String(n === index)); tab.tabIndex = n === index ? 0 : -1;
        select('#' + tab.getAttribute('aria-controls')).hidden = n !== index;
      });
      ['title','copy','now','next'].forEach((key,n) => { select('#hero-insight-' + key).textContent = insights[index][n]; });
      if (focus) tabs[index].focus();
    }
    tabs.forEach((tab,index) => {
      tab.addEventListener('click',() => activate(index,false));
      tab.addEventListener('keydown',event => {
        const key = event.key;
        if (!['ArrowRight','ArrowDown','ArrowLeft','ArrowUp','Home','End'].includes(key)) return;
        event.preventDefault(); activate(key === 'Home' ? 0 : key === 'End' ? 2 : (index + (['ArrowRight','ArrowDown'].includes(key) ? 1 : 2)) % 3,true);
      });
    });
  }

  function homepageCounts() {
    const nodes = selectAll('[data-count]'), running = new Map();
    const finish = node => { cancelAnimationFrame(running.get(node)); running.delete(node); node.textContent = node.dataset.count; };
    function animate(node) {
      const start = performance.now(), target = Number(node.dataset.count);
      const frame = now => {
        const progress = Math.min(1, Math.max(0,(now - start) / 1200));
        node.textContent = String(Math.round(target * (1 - (1 - progress) ** 3)));
        if (progress < 1) running.set(node,requestAnimationFrame(frame)); else running.delete(node);
      }; running.set(node,requestAnimationFrame(frame));
    }
    nodes.forEach(node => { node.textContent = '0'; });
    if (reducedMotion.matches) { nodes.forEach(finish); return; }
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver(entries => entries.forEach(entry => {
        if (entry.isIntersecting) { observer.unobserve(entry.target); animate(entry.target); }
      }),{threshold:.3});
      nodes.forEach(node => observer.observe(node));
      reducedMotion.addEventListener('change',() => { if (reducedMotion.matches) { observer.disconnect(); nodes.forEach(finish); } });
    } else nodes.forEach(animate);
    addEventListener('pagehide',() => nodes.forEach(finish));
  }

  // 入场：靠近视口时轻移显现一次，减少动态效果时直接显示。
  function revealSections() {
    if (reducedMotion.matches || !('IntersectionObserver' in window)) return;
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-in');
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -24px 0px' });
    selectAll('[data-reveal]').forEach((element) => observer.observe(element));
    document.documentElement.classList.add('motion-ready');
    reducedMotion.addEventListener('change', () => {
      observer.disconnect();
      document.documentElement.classList.remove('motion-ready');
    }, { once: true });
  }

  // 评分：同步原文、雷达与口径。
  function scoringEvidence() {
    const reasons = {
      depth: ['技术深度 · 覆盖了什么', '覆盖三个索引锚点；还没有解释磁盘 IO 与树高度的关系。下一问可以从这里展开。'],
      expression: ['表达逻辑 · 规则口径', '示例回答51字符，规则按长度估算为2.5分，不代表表达质量。'],
      match: ['岗位匹配 · 规则口径', '锚点覆盖率与回答长度加权为6.3分，不代表岗位胜任力。']
    };
    select('.dimension-list').addEventListener('click', (event) => {
      const button = event.target.closest('button[data-dimension]');
      if (!button) return;
      const key = button.dataset.dimension;
      selectAll('.dimension-list button').forEach((item) => item.setAttribute('aria-pressed', String(item === button)));
      selectAll('[data-evidence]').forEach((sentence) => sentence.classList.toggle('is-evidence', key === 'expression' || sentence.dataset.evidence === key));
      selectAll('.radar-vertices circle').forEach((vertex) => vertex.classList.toggle('is-active', vertex.dataset.dimension === key));
      select('#evidence-heading').textContent = reasons[key][0];
      select('#evidence-reason').textContent = reasons[key][1];
    });
  }

  // 配置：同步岗位、模式与主题。
  function practiceForm() {
    const form = select('#practice-form');
    const position = select('#position');
    const difficulty = select('#difficulty');
    const themes = select('#theme-options');
    const resumeText = select('#resume-text');
    const resumeFile = select('#resume-pdf');
    const error = select('#form-error');
    const dialog = select('#preview-dialog');
    const submit = form.querySelector('[type="submit"]');
    let themeLimit = 3;
    let busy = false;
    function resumeControls() {
      const file = resumeFile.files[0];
      resumeText.disabled = busy || !!file;
      select('#sample-resume').disabled = busy || !!file;
      select('#resume-remove').hidden = !file;
      select('#resume-pdf-status').textContent = file ? file.name + ' · ' + (file.size / 1024 / 1024).toFixed(2) + 'MB · 开始练习时上传' : '选择带文本层的 PDF，默认上限 5MB / 10页；点击开始后才上传。';
    }
    resumeFile.addEventListener('change', () => {
      const file = resumeFile.files[0];
      if (file && (!/\.pdf$/i.test(file.name) || (file.type && file.type !== 'application/pdf') || !file.size)) {
        resumeFile.value = ''; showError('请选择有效的 PDF 文件。');
      }
      resumeControls();
    });
    select('#resume-remove').addEventListener('click', () => { resumeFile.value = ''; resumeControls(); });
    const mode = () => form.elements.mode.value;
    const selectedThemes = () => selectAll('#theme-options input:checked').map((input) => input.value);
    const summary = () => catalog[position.value].name + ' / ' + difficulty.selectedOptions[0].textContent + ' / ' + (mode() === 'topic' ? '主题专项' : '综合面试');

    function updateSummary() {
      const topicMode = mode() === 'topic';
      const chosen = selectedThemes();
      select('#theme-field').hidden = !topicMode;
      select('#resume-field').hidden = topicMode;
      selectAll('#theme-options input').forEach((input) => { input.disabled = busy || (!input.checked && chosen.length >= themeLimit); });
      select('#form-summary').textContent = summary() + (topicMode && chosen.length ? ' · ' + chosen.join('、') : '');
      error.textContent = '';
    }

    function renderThemes() {
      themes.replaceChildren();
      catalog[position.value].themes.forEach((theme) => {
        const label = document.createElement('label');
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.name = 'themes';
        input.value = theme;
        label.append(input, document.createTextNode(theme));
        themes.append(label);
      });
      updateSummary();
    }

    position.addEventListener('change', renderThemes);
    form.addEventListener('change', updateSummary);
    resumeText.addEventListener('input', () => { select('#resume-count').textContent = resumeText.value.length.toLocaleString() + ' / 20,000 字'; });
    select('#sample-resume').addEventListener('click', () => {
      resumeText.value = position.value === 'java_backend'
        ? '专业技能：Java、MySQL、Redis。\n项目经历：订单查询服务，负责索引优化、缓存与事务设计。'
        : position.value === 'python_backend' ? '专业技能：Python、asyncio、SQL、FastAPI。\n项目经历：异步接口服务，处理参数绑定、事务与幂等。'
        : '经历背景：参与团队项目，负责沟通需求、制定计划并跟进执行。\n希望展开：我采取的行动、遇到的困难与最终结果。';
      resumeText.dispatchEvent(new Event('input'));
    });
    selectAll('[data-position-entry], [data-topic-entry]').forEach((link) => link.addEventListener('click', () => {
      if (link.dataset.positionEntry) { position.value = link.dataset.positionEntry; renderThemes(); }
      if (link.hasAttribute('data-topic-entry')) form.elements.mode.value = 'topic';
      updateSummary();
    }));
    select('#close-preview').addEventListener('click', () => dialog.close());

    function showError(message) {
      error.textContent = message;
      error.tabIndex = -1;
      error.focus();
    }

    // 接口：按需调用，凭据不进URL。
    async function request(path, options, extraHeaders) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 30000);
      try {
        const account = readAccount();
        const response = await guardedFetch(document.body.dataset.api.replace(/\/$/, '') + path, {
          ...options, signal: controller.signal, cache: 'no-store',
          headers: { ...(options?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
            ...(account ? { Authorization: 'Bearer ' + account.access_token } : {}), ...extraHeaders }
        });
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : '请求失败，请检查输入后重试。');
        return data;
      } catch (failure) {
        if (failure.name === 'AbortError') throw new Error('请求超时，请到练习记录确认是否已创建，再决定是否重试。');
        if (failure instanceof TypeError) throw new Error('暂时无法连接服务，请稍后再试。');
        throw failure;
      } finally { clearTimeout(timer); }
    }

    const readAccount = readSession;

    function saveCredential(kind, resource) {
      if (!/^[a-f0-9]{32}$/.test(resource[kind + '_id'])) throw new Error('服务响应格式不正确，请检查接口。');
      if (resource.access_token) {
        if (!/^[a-f0-9]{64}$/.test(resource.access_token)) throw new Error('服务响应凭据格式不正确。');
        sessionStorage.setItem(kind + ':' + resource[kind + '_id'] + ':token', resource.access_token);
      } else if (!resource.account_owned || !readAccount()) throw new Error('服务未返回有效访问凭据。');
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (busy) return;
      const chosen = selectedThemes();
      const topicMode = mode() === 'topic';
      if (topicMode && (!chosen.length || chosen.length > themeLimit)) return showError('请选择1至' + themeLimit + '个知识主题。');
      if (!document.body.dataset.api) {
        select('#preview-selection').textContent = summary();
        select('#preview-detail').textContent = topicMode ? '选定主题：' + chosen.join('、') + '。每主题最多2道主问题，保留追问。' : '可围绕岗位展开多主题问答；实际大纲由接入后的服务端生成。';
        dialog.showModal();
        return;
      }
      const destination = new URL(document.body.dataset.workspaceBase || '/', location.href);
      if (destination.origin !== location.origin) return showError('请先配置同源练习室。');
      try {
        sessionStorage.setItem('home-storage-check', '1');
        sessionStorage.removeItem('home-storage-check');
      } catch { return showError('无法保存凭据，请允许本站会话存储。'); }
      busy = true;
      const controls = Array.from(form.querySelectorAll('input, select, textarea, button'));
      controls.forEach((control) => { control.disabled = true; });
      submit.textContent = '正在准备练习…';
      try {
        const available = await request('/positions');
        const role = available.positions.find((item) => item.id === position.value);
        if (!role) throw new Error('该岗位当前不可用，请刷新页面后重试。');
        themeLimit = role.practice_theme_limit;
        if (topicMode && (chosen.length > themeLimit || chosen.some((theme) => !role.practice_themes.includes(theme)))) throw new Error('主题已更新，请刷新后重选。');
        const payload = { position: position.value, difficulty: difficulty.value };
        let resumeToken = '';
        if (topicMode) payload.themes = chosen;
        else if (resumeFile.files[0] || resumeText.value.trim()) {
          let body, path = '/resume';
          if (resumeFile.files[0]) {
            const limits = await request('/resume/limits');
            if (resumeFile.files[0].size > limits.pdf_max_bytes) throw new Error('PDF 超过服务上限（' + Math.round(limits.pdf_max_bytes / 1024 / 1024) + 'MB），请压缩后重试。');
            body = new FormData(); body.append('file', resumeFile.files[0]); body.append('name', '匿名用户'); path = '/resume/pdf';
            submit.textContent = '正在解析 PDF 简历…';
          } else body = JSON.stringify({ name: '匿名用户', resume_text: resumeText.value });
          const resume = await request(path, { method: 'POST', body });
          saveCredential('resume', resume);
          payload.resume_id = resume.resume_id;
          resumeToken = resume.access_token || readAccount()?.access_token || '';
        }
        const created = await request('/interview', { method: 'POST', body: JSON.stringify(payload) }, { 'X-Resume-Token': resumeToken });
        saveCredential('interview', created);
        location.assign(destination.pathname.replace(/\/$/, '') + '/interview/' + created.interview_id);
      } catch (failure) { showError(failure.message || '创建失败，请稍后再试。'); }
      finally {
        busy = false;
        controls.forEach((control) => { control.disabled = false; });
        resumeControls();
        submit.textContent = '开始模拟面试';
        selectAll('#theme-options input').forEach((input) => { input.disabled = !input.checked && selectedThemes().length >= themeLimit; });
      }
    });
    if (document.body.dataset.api) {
      submit.textContent = '开始模拟面试';
      select('.cta-note').textContent = '点击开始后，才会提交所选配置及填写的简历。';
    }
    renderThemes();
    resumeControls();
    submit.disabled = false;
  }

  // 入口：替换链接，不预取页面。
  function workspaceLinks() {
    const base = (document.body.dataset.workspaceBase || '').replace(/\/$/, '');
    selectAll('[data-workspace-path]').forEach((link) => { link.href = base + link.dataset.workspacePath; });
  }

  function accountCarousel() {
    const find = id => select('#carousel-' + id);
    const defaults = [
      { scene: 'discover', title: '找到值得练习的下一题', copy: '从六个方向探索题库，选择适合自己的岗位与主题。', label: '01 / 发现方向', action: '探索题库', href: '/catalog' },
      { scene: 'practice', title: '把思路说出来，再往深处问', copy: '文字作答、实时交流或语音输入，按自己的节奏组织答案。', label: '02 / 开始练习', action: '配置一场练习', href: '/#start' },
      { scene: 'review', title: '把这一次的收获，留给下一次', copy: '登录后保存练习记录、查看报告，并安排自己的复习计划。', label: '03 / 回看与复习', action: '登录并查看记录', href: '/account?next=%2Fhistory' }
    ];
    let identity, rows = [], index = 0, paused = reducedMotion.matches, generation = 0;
    function clear() {
      rows = defaults; index = 0; generation++;
      for (const key of ['finished','todo','notes']) find(key).textContent = '0';
      controls(); show();
    }
    function controls() {
      for (const key of ['prev','next','pause']) find(key).disabled = rows.length < 2;
      find('pause').textContent = paused ? '继续轮播' : '暂停轮播';
    }
    function show(manual = false) {
      if (!rows.length) return;
      if ((readSession()?.access_token || '') !== identity) { refresh(); return; }
      const row = rows[index], title = document.createElement('h3'), copy = document.createElement('p'), link = document.createElement('a');
      const art = document.createElement('div'), content = document.createElement('div'), label = document.createElement('p');
      art.className = 'carousel-art scene-' + (row.scene || 'review'); art.setAttribute('aria-hidden','true');
      for (let n = 0; n < 3; n++) art.append(document.createElement('span'));
      content.className = 'carousel-copy'; label.className = 'eyebrow';
      title.textContent = row.title || row.position_display_name || row.position;
      label.textContent = row.label || '你的练习记录';
      copy.textContent = row.copy || '已保存 ' + row.answer_count + ' 轮 · ' + (row.status === 'finished' ? '已完成' : '继续练习');
      link.textContent = row.action || (row.status === 'finished' ? '回看报告' : '继续这场练习'); link.className = 'notes-button';
      link.href = row.href || (row.status === 'finished' ? '/report/' : '/interview/') + row.interview_id;
      content.append(label, title, copy, link);
      find('slide').setAttribute('aria-live', manual ? 'polite' : 'off');
      find('slide').replaceChildren(art, content); find('page').textContent = (index + 1) + ' / ' + rows.length;
    }
    function count(key, target, version) {
      const start = performance.now(); target = Math.max(0, Number(target) || 0);
      const frame = time => {
        if (version !== generation) return;
        const progress = reducedMotion.matches ? 1 : Math.min(1, (time - start) / 850);
        find(key).textContent = String(Math.round(target * (1 - (1 - progress) ** 3)));
        if (progress < 1) requestAnimationFrame(frame);
      }; requestAnimationFrame(frame);
    }
    async function refresh() {
      const account = readSession(), next = account?.access_token || '';
      if (next === identity) return;
      identity = next; clear();
      find('status').textContent = account ? '正在读取你的记录，先看看练习指南。' : '练习指南 · 登录后自动切换为你的记录，数字为账户实际数据。';
      if (!account) return;
      const version = generation;
      try {
        const response = await guardedFetch('/api/account/dashboard', {cache:'no-store',signal:AbortSignal.timeout(10000),headers:{Authorization:'Bearer ' + next}});
        const data = await response.json();
        if (version !== generation) return;
        if (!response.ok) throw new Error('记录暂不可用，请到练习概览重试。');
        const records = [...data.active, ...data.recent].filter(row => row.answer_count > 0 && /^[a-f0-9]{32}$/.test(row.interview_id));
        rows = records.length ? records : defaults;
        find('status').textContent = records.length ? '当前账户的最近记录，支持手动切换。' : '还没有已作答记录，先跟着指南开始一场练习吧。';
        count('finished',data.interviews.finished,version);count('todo',data.tasks.todo,version);count('notes',data.notes_with_content,version);
        controls();
        show();
      } catch { if (version === generation) {clear(); find('status').textContent = '暂时无法读取记录，当前展示练习指南。';} }
    }
    for (const [key,step] of [['prev',-1],['next',1]]) find(key).addEventListener('click',()=>{index=(index+step+rows.length)%rows.length;show(true);});
    find('pause').addEventListener('click',()=>{paused=!paused;find('pause').textContent=paused?'继续轮播':'暂停轮播';});
    reducedMotion.addEventListener('change',()=>{paused=reducedMotion.matches;find('pause').textContent=paused?'继续轮播':'暂停轮播';});
    let hovered=false;
    select('.account-carousel').addEventListener('mouseenter',()=>{hovered=true;});
    select('.account-carousel').addEventListener('mouseleave',()=>{hovered=false;});
    select('.account-carousel').addEventListener('keydown', event => {
      if (!['ArrowLeft','ArrowRight'].includes(event.key)) return;
      event.preventDefault(); index = (index + (event.key === 'ArrowRight' ? 1 : rows.length - 1)) % rows.length; show(true);
    });
    let timer;
    function startTimer() { clearInterval(timer); timer=setInterval(()=>{
      if ((readSession()?.access_token||'')!==identity) {refresh();return;}
      if (!paused&&!hovered&&!document.hidden&&!select('.account-carousel').contains(document.activeElement)&&rows.length>1) {index=(index+1)%rows.length;show();}
    },6000); }
    addEventListener('pagehide',()=>clearInterval(timer));
    addEventListener('focus',refresh);addEventListener('pageshow',()=>{identity=undefined;startTimer();refresh();});startTimer();refresh();
  }

  // 初始化：模块独立启用，局部失败不影响其他功能。
  [navigation, heroDemo, homepageCounts, questionDemo, revealSections, scoringEvidence, practiceForm, workspaceLinks, accountCarousel].forEach((initialize) => {
    try { initialize(); }
    catch { document.documentElement.classList.add('partial-interaction'); }
  });
})();
