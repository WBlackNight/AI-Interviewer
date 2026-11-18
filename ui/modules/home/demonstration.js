  // 演示：点击或方向键切换环节。
  function demoTabs(tabs, { vertical = false, onChange, autoPlay = false } = {}) {
    let current = 0;
    let reschedule = () => {};
    function activate(index, focus) {
      if (index === current) return;
      const direction = index > current ? 'next' : 'previous';
      current = index;
      tabs.forEach((tab, position) => {
        const active = position === index;
        tab.setAttribute('aria-selected', String(active));
        tab.tabIndex = active ? 0 : -1;
        const panel = select('#' + tab.getAttribute('aria-controls'));
        if (active) panel.setAttribute('data-direction', direction);
        panel.hidden = !active;
      });
      onChange?.(index);
      if (focus) tabs[index].focus();
      reschedule();
    }
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => activate(index, false));
      tab.addEventListener('keydown', (event) => {
        let next = index;
        if (event.key === 'ArrowRight' || vertical && event.key === 'ArrowDown') next = (index + 1) % tabs.length;
        else if (event.key === 'ArrowLeft' || vertical && event.key === 'ArrowUp') next = (index + tabs.length - 1) % tabs.length;
        else if (event.key === 'Home') next = 0;
        else if (event.key === 'End') next = tabs.length - 1;
        else return;
        event.preventDefault();
        activate(next, true);
      });
    });
    if (autoPlay && typeof IntersectionObserver === 'function') {
      const root = tabs[0].closest('.hero-visual');
      let timer, visible = false, hovered = false, focused = false, disposed = false;
      reschedule = () => {
        clearTimeout(timer);
        if (!visible || hovered || focused || disposed || document.hidden || reducedMotion.matches || compactHome.matches) return;
        timer = setTimeout(() => activate((current + 1) % tabs.length, false), 4800);
      };
      const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; reschedule(); }, {threshold: .2});
      observer.observe(root);
      root.addEventListener('mouseenter', () => { hovered = true; reschedule(); });
      root.addEventListener('mouseleave', () => { hovered = false; reschedule(); });
      root.addEventListener('focusin', () => { focused = true; reschedule(); });
      root.addEventListener('focusout', event => { focused = root.contains(event.relatedTarget); reschedule(); });
      document.addEventListener('visibilitychange', reschedule);
      reducedMotion.addEventListener('change', reschedule);
      compactHome.addEventListener('change', reschedule);
      addEventListener('pagehide', () => { disposed = true; clearTimeout(timer); });
      addEventListener('pageshow', () => { disposed = false; reschedule(); });
    }
  }

  function questionDemo() { demoTabs(selectAll('.demo-tabs [role="tab"]')); }

  function heroDemo() {
    const insights = [
      ['从“知道”，到说得有依据。','连接数据结构与查询成本，让思路再往前一步。','范围查询','解释原因与边界'],
      ['沿着遗漏，再问深一点。','从回答里尚未展开的部分，找到下一层追问。','磁盘 IO 与树高度','补上结论背后的原因'],
      ['把复盘，变成下一步。','回看回答和评分要点，把薄弱主题留给下一次练习。','已覆盖 3 / 4 要点','安排一次主题复习']
    ];
    demoTabs(selectAll('[data-hero-step]'), {
      vertical: true,
      autoPlay: true,
      onChange(index) {
        ['title','copy','now','next'].forEach((key,n) => { select('#hero-insight-' + key).textContent = insights[index][n]; });
      }
    });
  }
