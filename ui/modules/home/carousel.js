  function accountCarousel() {
    const find = id => select('#carousel-' + id);
    const defaults = [
      { scene: 'discover', title: '找到值得练习的下一题', copy: '探索岗位与主题，选择适合自己的练习方向。', label: '01 / 发现方向', action: '探索题库', href: '/catalog' },
      { scene: 'practice', title: '把思路说出来，再往深处问', copy: '文字作答、实时交流或语音输入，按自己的节奏组织答案。', label: '02 / 开始练习', action: '配置一场练习', href: '/#start' },
      { scene: 'review', title: '把这一次的收获，留给下一次', copy: '登录后保存练习记录、查看报告，并安排自己的复习计划。', label: '03 / 回看与复习', action: '登录并查看记录', href: '/account?next=%2Fhistory' }
    ];
    let identity, rows = [], index = 0, generation = 0;
    function clear() {
      rows = defaults; index = 0; generation++;
      find('metrics')?.removeAttribute('data-account-ready');
      for (const key of ['finished','todo','notes']) find(key).textContent = '0';
      controls(); show();
    }
    function controls() {
      for (const key of ['prev','next']) find(key).disabled = rows.length < 2;
    }
    function show(direction = 0, manual = false) {
      if (!rows.length) return;
      if ((readSession()?.access_token || '') !== identity) { refresh(); return; }
      const row = rows[index], title = document.createElement('h3'), copy = document.createElement('p'), link = document.createElement('a');
      const art = document.createElement('div'), content = document.createElement('div'), label = document.createElement('p');
      art.className = 'carousel-art scene-' + (row.scene || 'review'); art.setAttribute('aria-hidden','true');
      for (let n = 0; n < 3; n++) art.append(document.createElement('span'));
      content.className = 'carousel-copy'; label.className = 'eyebrow';
      if (direction) {
        const movement = direction > 0 ? 'next' : 'previous';
        art.setAttribute('data-direction', movement);
        content.setAttribute('data-direction', movement);
      }
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
      const node = find(key), start = performance.now(); target = Math.max(0, Number(target) || 0);
      if (reducedMotion.matches) { node.textContent = String(target); return; }
      const frame = time => {
        if (version !== generation) return;
        const progress = reducedMotion.matches ? 1 : Math.min(1, (time - start) / 850);
        node.textContent = String(Math.round(target * (1 - (1 - progress) ** 3)));
        if (progress < 1) requestAnimationFrame(frame);
      }; requestAnimationFrame(frame);
    }
    async function refresh() {
      const account = readSession(), next = account?.access_token || '';
      if (next === identity) return;
      identity = next; clear();
      find('status').textContent = account ? '正在读取练习记录…' : '登录后可以在这里继续练习，也可直接开始。';
      if (!account) return;
      const version = generation;
      try {
        const response = await guardedFetch('/api/account/dashboard', {cache:'no-store',signal:AbortSignal.timeout(10000),headers:{Authorization:'Bearer ' + next}});
        const data = await response.json();
        if (version !== generation) return;
        if (!response.ok) throw new Error('记录暂不可用，请到练习概览重试。');
        const records = [...data.active, ...data.recent].filter(row => row.answer_count > 0 && /^[a-f0-9]{32}$/.test(row.interview_id));
        rows = records.length ? records : defaults;
        find('metrics')?.setAttribute('data-account-ready', '');
        find('status').textContent = records.length ? '当前账户的最近记录，支持手动切换。' : '还没有已作答记录，先跟着指南开始一场练习吧。';
        count('finished',data.interviews.finished,version);count('todo',data.tasks.todo,version);count('notes',data.notes_with_content,version);
        controls();
        show();
      } catch { if (version === generation) {clear(); find('status').textContent = '暂时无法读取记录，当前展示练习指南。';} }
    }
    function move(step, manual = false) {
      if (rows.length < 2) return;
      index = (index + step + rows.length) % rows.length;
      show(step, manual);
      if (manual) startTimer();
    }
    for (const [key, step] of [['prev', -1], ['next', 1]]) find(key).addEventListener('click', () => move(step, true));
    const carousel = select('.account-carousel');
    let hovered = false, inView = typeof IntersectionObserver === 'undefined';
    if (!inView) new IntersectionObserver(([entry]) => { inView = entry.isIntersecting; }).observe(find('slide'));
    carousel.addEventListener('mouseenter', () => { hovered = true; });
    carousel.addEventListener('mouseleave', () => { hovered = false; });
    carousel.addEventListener('keydown', event => {
      if (!['ArrowLeft','ArrowRight'].includes(event.key)) return;
      event.preventDefault(); move(event.key === 'ArrowRight' ? 1 : -1, true);
    });
    let timer;
    function startTimer() { clearInterval(timer); if (compactHome.matches) return; timer=setInterval(()=>{
      if ((readSession()?.access_token||'')!==identity) {refresh();return;}
      if (inView && !reducedMotion.matches && !hovered && !document.hidden && !carousel.contains(document.activeElement)) move(1);
    },4200); }
    addEventListener('pagehide',()=>clearInterval(timer));
    compactHome.addEventListener('change', startTimer);
    addEventListener('account:changed', refresh);
    addEventListener('account:expired', refresh);
    addEventListener('focus',refresh);addEventListener('pageshow',()=>{identity=undefined;startTimer();refresh();});startTimer();refresh();
  }
