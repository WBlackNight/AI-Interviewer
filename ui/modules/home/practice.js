  // 配置：同步岗位、模式与主题。
  function practiceForm() {
    const form = select('#practice-form');
    const position = select('#position');
    const difficulty = select('#difficulty');
    const duration = select('#practice-duration');
    const themes = select('#theme-options');
    const resumeText = select('#resume-text');
    const resumeFile = select('#resume-pdf');
    const error = select('#form-error');
    const dialog = select('#preview-dialog');
    const confirmStart = select('#preview-confirm');
    const submit = form.querySelector('[type="submit"]');
    let themeLimit = 3;
    let busy = false;
    let confirmed = false;
    let previewIdentity = '';
    let submissionIdentity = '';
    function invalidPdf(file) {
      return file && (!/\.pdf$/i.test(file.name) || (file.type && file.type !== 'application/pdf') || !file.size);
    }
    function resumeControls() {
      const file = resumeFile.files[0];
      const invalid = invalidPdf(file);
      resumeFile.setAttribute('aria-invalid', invalid ? 'true' : 'false');
      resumeText.disabled = busy || !!file;
      select('#sample-resume').disabled = busy || !!file;
      select('#resume-done').disabled = busy || !!file;
      if (file) select('#resume-completion').textContent = '';
      select('#resume-remove').hidden = !file;
      select('#resume-pdf-status').textContent = invalid ? '文件无效。请选择非空 PDF，或移除该文件。' : file ? file.name + ' · ' + (file.size / 1024 / 1024).toFixed(2) + 'MB · 确认后上传' : '请选择带文本层的 PDF。';
    }
    resumeFile.addEventListener('change', resumeControls);
    select('#resume-remove').addEventListener('click', () => { resumeFile.value = ''; error.textContent = ''; resumeControls(); resumeFile.focus(); });
    const mode = () => form.elements.mode.value;
    const selectedThemes = () => selectAll('#theme-options input:checked').map((input) => input.value);
    const intent = () => ({ position: position.value, difficulty: difficulty.value,
      duration: duration.value, mode: mode(), themes: selectedThemes() });
    function saveIntent() {
      if (!busy) history.replaceState(null, '', location.pathname + '?' + practiceIntentQuery(intent()) + location.hash);
    }
    const summary = () => catalog[position.value].name + ' / ' + difficulty.selectedOptions[0].textContent + ' / ' + (mode() === 'topic' ? '主题专项' : '综合面试') + ' / ' + duration.selectedOptions[0].textContent;

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
    form.addEventListener('change', () => { updateSummary(); saveIntent(); });
    resumeText.addEventListener('input', () => { select('#resume-count').textContent = resumeText.value.length.toLocaleString() + ' / 20,000 字'; });
    select('#sample-resume').addEventListener('click', () => {
      resumeText.value = position.value === 'java_backend'
        ? '专业技能：Java、MySQL、Redis。\n项目经历：订单查询服务，负责索引优化、缓存与事务设计。'
        : position.value === 'python_backend' ? '专业技能：Python、asyncio、SQL、FastAPI。\n项目经历：异步接口服务，处理参数绑定、事务与幂等。'
        : '经历背景：参与团队项目，负责沟通需求、制定计划并跟进执行。\n希望展开：我采取的行动、遇到的困难与最终结果。';
      resumeText.dispatchEvent(new Event('input'));
    });
    selectAll('[data-position-entry], [data-topic-entry], [data-practice-mode]').forEach((link) => link.addEventListener('click', () => {
      if (busy) return;
      if (link.dataset.positionEntry) { position.value = link.dataset.positionEntry; renderThemes(); }
      if (link.hasAttribute('data-topic-entry')) form.elements.mode.value = 'topic';
      if (link.dataset.practiceMode) form.elements.mode.value = link.dataset.practiceMode;
      if (mode() === 'topic') select('#practice-options').open = true;
      updateSummary();
      form.dispatchEvent(new Event('change', { bubbles: true }));
    }));
    select('#practice-copy').addEventListener('click', async () => {
      const status = select('#practice-copy-status');
      const url = location.origin + location.pathname + '?' + practiceIntentQuery(intent()) + '#start';
      try {
        await navigator.clipboard.writeText(url);
        status.textContent = '已复制配置链接，只包含岗位、主题、强度与用时。';
        notify('练习配置已复制');
      } catch { status.textContent = '暂时无法复制，可直接复制浏览器地址分享配置。'; notify('复制失败，请复制浏览器地址', 'error'); }
    });
    select('#close-preview').addEventListener('click', () => dialog.close());
    select('#preview-back').addEventListener('click', () => dialog.close());
    confirmStart.addEventListener('click', () => {
      dialog.close();
      if ((readAccount()?.access_token || '') !== previewIdentity) return showError('登录状态已变化，请重新确认练习配置。');
      confirmed = true;
      try { form.requestSubmit(); } finally { confirmed = false; }
    });

    function showError(message) {
      error.textContent = message;
      notify(message, 'error');
      error.tabIndex = -1;
      error.focus();
    }

    // 接口：按需调用，凭据不进URL。
    async function request(path, options, extraHeaders) {
      const current = readAccount()?.access_token || '';
      if (current !== submissionIdentity) throw new Error('登录状态已变化，请重新确认练习配置。');
      try {
        const data = await requestJSON(document.body.dataset.api.replace(/\/$/, '') + path, {
          ...options, auth: !!current, timeout: 30000,
          headers: { ...(options?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...extraHeaders }
        });
        if ((readAccount()?.access_token || '') !== submissionIdentity) throw new Error('登录状态已变化，请重新确认练习配置。');
        return data;
      } catch (error) {
        if (error.code === 'TIMEOUT') throw new Error('请求超时，请到练习记录确认是否已创建，再决定是否重试。');
        throw error;
      }
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
      if (topicMode && (!chosen.length || chosen.length > themeLimit)) {
        select('#practice-options').open = true;
        return showError('请选择1至' + themeLimit + '个知识主题。');
      }
      const file = topicMode ? null : resumeFile.files[0];
      const hasResume = !topicMode && (file || resumeText.value.trim());
      if (invalidPdf(file)) {
        select('#resume-field').open = true;
        return showError('文件无效。请选择非空 PDF，或移除该文件。');
      }
      const live = !!document.body.dataset.api;
      if (!live || (hasResume && !confirmed)) {
        previewIdentity = readAccount()?.access_token || '';
        select('#preview-selection').textContent = summary();
        select('#preview-detail').textContent = topicMode ? '选定主题：' + chosen.join('、') : file ? '简历文件：' + file.name : hasResume ? '简历：已填写文本' : '简历：未提供';
        select('#preview-note').textContent = live ? '确认后将上传所选简历，并以这些配置创建练习。' : '当前为配置预览，尚未上传简历或创建练习。';
        confirmStart.hidden = !live;
        select('#preview-workspace').hidden = live;
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
      submissionIdentity = readAccount()?.access_token || '';
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
        if (duration.value) payload.duration_minutes = Number(duration.value);
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
        notify('练习已准备好，可以开始作答', 'success', true);
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
    function restoreIntent() {
      if (busy) return;
      const stored = readPracticeIntent(location.search, catalog, themeLimit);
      position.value = stored.position; difficulty.value = stored.difficulty;
      duration.value = location.search ? stored.duration : '5'; form.elements.mode.value = stored.mode;
      renderThemes();
      selectAll('#theme-options input').forEach(input => { input.checked = stored.themes.includes(input.value); });
      updateSummary();
    }
    addEventListener('popstate', restoreIntent);
    restoreIntent();
    resumeControls();
    submit.disabled = false;
  }
