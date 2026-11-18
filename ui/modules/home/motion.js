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
    let observer;
    if ('IntersectionObserver' in window) {
      observer = new IntersectionObserver(entries => entries.forEach(entry => {
        if (entry.isIntersecting) { observer.unobserve(entry.target); animate(entry.target); }
      }),{threshold:.3});
      nodes.forEach(node => observer.observe(node));
    } else nodes.forEach(animate);
    function finishAll() { observer?.disconnect(); nodes.forEach(finish); }
    reducedMotion.addEventListener('change', () => { if (reducedMotion.matches) finishAll(); });
    addEventListener('pagehide', finishAll);
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
