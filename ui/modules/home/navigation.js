  // Move the same form so visual and keyboard order agree at both widths.
  function mobileHome() {
    const start = select('#start');
    if (!start) return;
    const hero = select('.hero');
    const end = start.parentNode;
    const options = select('#practice-options');
    function arrange() {
      const focused = document.activeElement;
      if (start.contains(focused)) return;
      if (compactHome.matches) {
        if (hero.nextElementSibling !== start) hero.after(start);
      } else if (end.lastElementChild !== start) end.append(start);
    }
    arrange();
    compactHome.addEventListener('change', arrange);
    start.addEventListener('focusout', event => { if (!start.contains(event.relatedTarget)) queueMicrotask(arrange); });
    function revealIntent() {
      const intent = new URLSearchParams(location.search);
      if (intent.get('mode') === 'topic' || intent.has('theme') || ['easy', 'hard'].includes(intent.get('difficulty'))) options.open = true;
    }
    revealIntent();
    addEventListener('popstate', revealIntent);
    for (const link of selectAll('.hero-actions [href="#start"]')) {
      link.addEventListener('click', () => { select('#cta-title').focus({ preventScroll: true }); });
    }
  }

  // 导航：同步菜单状态与吸顶边线。
  function navigation() {
    const header = select('#nav');
    let pending = false;
    function updateBorder() {
      pending = false;
      header.classList.toggle('is-stuck', scrollY > 80);
    }
    addEventListener('scroll', () => {
      if (!pending) { pending = true; requestAnimationFrame(updateBorder); }
    }, { passive: true });
    updateBorder();
  }


  // 入口：替换链接，不预取页面。
  function workspaceLinks() {
    const base = (document.body.dataset.workspaceBase || '').replace(/\/$/, '');
    selectAll('[data-workspace-path]').forEach((link) => { link.href = base + link.dataset.workspacePath; });
  }
  function deviceHome() {
    const touch = matchMedia('(pointer: coarse)');
    const mobileAgent = navigator.userAgentData?.mobile === true ||
      /iPhone|iPod|Android.*Mobile/i.test(navigator.userAgent);
    const tabletAgent = /iPad|Android/i.test(navigator.userAgent) ||
      (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    const label = select('#home-device');
    function update() {
      const compact = compactHome.matches;
      const device = mobileAgent ? 'mobile' :
        tabletAgent || touch.matches ? 'touch' : 'desktop';
      document.documentElement.dataset.device = device;
      document.documentElement.dataset.homeLayout = compact ? 'compact' : 'wide';
      const prefix = { mobile: '手机 · ', touch: '触屏 · ', desktop: compact ? '' : '电脑 · ' };
      label.textContent = prefix[device] + (compact ? '移动布局' : '桌面布局');
    }
    update();
    compactHome.addEventListener('change', update);
    touch.addEventListener('change', update);
  }

