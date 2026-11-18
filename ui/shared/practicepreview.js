  function practicePreview() {
    if (!document.body.dataset.api) return;
    const form = select('#practice-form'), summary = select('#practice-preview');
    let controller, timer, generation = 0;
    async function update() {
      const version = ++generation;
      controller?.abort(); controller = new AbortController();
      const requestController = controller;
      const themes = selectAll('#theme-options input:checked').map(input => input.value);
      const topic = form.elements.mode.value === 'topic';
      if (topic && !themes.length) { summary.textContent = '选择主题后，在这里查看本场安排。'; summary.removeAttribute('aria-busy'); return; }
      const payload = { position: select('#position').value, difficulty: select('#difficulty').value };
      const minutes = select('#practice-duration').value;
      if (minutes) payload.duration_minutes = Number(minutes);
      if (topic) payload.themes = themes;
      summary.setAttribute('aria-busy', 'true');
      summary.textContent = '正在安排本场主题…';
      const deadline = setTimeout(() => requestController.abort(), 8000);
      try {
        const data = await requestJSON('/api/practice/preview', { method: 'POST', signal: requestController.signal,
          headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if (version !== generation) return;
        summary.textContent = data.themes.map(item => item.name + ' ' + item.question_count + '题').join(' · ') +
          '。共 ' + data.main_question_count + ' 道主问题' + (data.includes_coding ? '，另有编程环节' : '') + '。' + data.note;
      } catch {
        if (version === generation) summary.textContent = '暂时无法预览安排，可稍后重新选择配置。';
      } finally {
        clearTimeout(deadline);
        if (version === generation) summary.removeAttribute('aria-busy');
      }
    }
    form.addEventListener('change', () => {
      clearTimeout(timer); controller?.abort(); generation++;
      timer = setTimeout(update, 240);
    });
    addEventListener('popstate', () => { clearTimeout(timer); void update(); });
    addEventListener('pagehide', () => { clearTimeout(timer); generation++; controller?.abort(); });
    if (compactHome.matches && typeof IntersectionObserver === 'function') {
      const observer = new IntersectionObserver(([entry]) => {
        if (!entry.isIntersecting) return;
        observer.disconnect();
        void update();
      });
      observer.observe(form);
    } else void update();
  }
