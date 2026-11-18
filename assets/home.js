/* Generated: tools/build_ui.py */
/* 青栈首页：原生DOM，无依赖。 */
(function () {
	'use strict';
function notify(message, type = 'success', nextPage = false) {
	const detail = { message: String(message || '').slice(0, 240), type };
	if (!detail.message) return;
	if (nextPage) {
		try { sessionStorage.setItem('ui:notice', JSON.stringify({ ...detail, expires: Date.now() + 10000 })); } catch {}
	} else if (typeof CustomEvent === 'function') dispatchEvent(new CustomEvent('app:notice', { detail }));
}
function readSession() {
	try {
		const value = JSON.parse(sessionStorage.getItem('account:session'));
		return value && /^[a-f0-9]{64}$/.test(value.access_token)
			&& /^[a-f0-9]{32}$/.test(value.account?.id)
			&& typeof value.account.username === 'string'
			&& Date.parse(value.expires_at) > Date.now() ? value : null;
	} catch { return null; }
}
async function guardedFetch(url, options) {
	const identity = readSession()?.access_token || '';
	const response = await fetch(url, options);
	const read = response.json.bind(response);
	response.json = async () => {
		const data = await read();
		if ((readSession()?.access_token || '') !== identity) throw Object.assign(new Error('会话已变化，请重新读取。'), { status: 401 });
		return data;
	};
	return response;
}
async function requestJSON(path, { auth = false, timeout = 10000, signal, ...options } = {}) {
	const identity = auth ? readSession()?.access_token : '';
	if (auth && !identity) throw Object.assign(new Error('请先登录后继续。'), { status: 401 });
	const controller = new AbortController();
	const cancel = () => controller.abort();
	if (signal?.aborted) cancel(); else signal?.addEventListener('abort', cancel, { once: true });
	const timer = setTimeout(cancel, timeout);
	const ensureIdentity = () => {
		if (auth && readSession()?.access_token !== identity) {
			throw Object.assign(new Error('账户已变化，请重新读取。'), { status: 401 });
		}
	};
	try {
		const response = await fetch(path, { ...options, cache: 'no-store', signal: controller.signal,
			headers: { ...(auth ? { Authorization: 'Bearer ' + identity } : {}), ...options.headers } });
		ensureIdentity();
		let data;
		try { data = await response.json(); }
		catch (error) { if (error.name === 'AbortError') throw error; throw new Error('返回内容暂时无法读取，请重试。'); }
		ensureIdentity();
		if (!response.ok) throw Object.assign(new Error(typeof data?.detail === 'string' ? data.detail :
			response.status === 401 ? '登录已过期，请重新登录。' : '操作暂未完成，请稍后重试。'), { status: response.status });
		return data;
	} catch (error) {
		if (error.name === 'AbortError' && !signal?.aborted) throw Object.assign(new Error('等待超时，请稍后重试。'), { code: 'TIMEOUT' });
		if (error instanceof TypeError) throw new Error('连接暂时中断，请检查网络后重试。');
		throw error;
	} finally {
		clearTimeout(timer);
		signal?.removeEventListener('abort', cancel);
	}
}
function readPracticeIntent(search, roles, limit = 3) {
	const query = new URLSearchParams(search);
	const position = Object.hasOwn(roles, query.get('position')) ? query.get('position') : Object.keys(roles)[0];
	const themes = [...new Set(query.getAll('theme'))].filter(theme => roles[position]?.themes.includes(theme)).slice(0, limit);
	return { position, difficulty: ['easy', 'mid', 'hard'].includes(query.get('difficulty')) ? query.get('difficulty') : 'mid',
		duration: ['5', '10', '15'].includes(query.get('duration')) ? query.get('duration') : '',
		mode: query.get('mode') === 'topic' || themes.length ? 'topic' : 'general', themes };
}
function practiceIntentQuery(intent) {
	const query = new URLSearchParams({ position: intent.position, difficulty: intent.difficulty, mode: intent.mode });
	if (intent.duration) query.set('duration', intent.duration);
	if (intent.mode === 'topic') intent.themes.forEach(theme => query.append('theme', theme));
	return query;
}
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
	const select = (selector) => document.querySelector(selector);
	const selectAll = (selector) => Array.from(document.querySelectorAll(selector));
	const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
	const compactHome = matchMedia('(max-width: 700px), (max-width: 950px) and (pointer: coarse)');
	const catalog = {"java_backend": {"name": "Java 后端", "group": "技术研发", "summary": "从语言基础到并发、数据存储与服务设计。", "focus": "原理、边界与工程取舍", "count": 20, "themes": ["Java基础", "MySQL", "并发编程", "JVM", "Spring", "Redis", "计算机网络"]}, "python_backend": {"name": "Python 后端", "group": "技术研发", "summary": "围绕 Python、异步编程与接口服务展开。", "focus": "实现思路与可靠性", "count": 20, "themes": ["Python基础", "Web与数据", "异步与并发"]}, "marketing": {"name": "市场营销", "group": "业务与管理", "summary": "练习用户定位、品牌传播与活动效果分析。", "focus": "目标、行动与效果", "count": 20, "themes": ["内容与渠道", "品牌与协作", "用户与定位", "活动与评估"]}, "operations": {"name": "运营管理", "group": "业务与管理", "summary": "梳理流程协作、用户服务与数据增长案例。", "focus": "问题分析与落地改进", "count": 20, "themes": ["数据与增长", "项目与风险", "流程与协作", "服务与改进"]}, "education": {"name": "教育教学", "group": "教育与语言", "summary": "通过教学设计、课堂场景与评价练习表达。", "focus": "情境判断与沟通", "count": 20, "themes": ["教学设计", "沟通与评价", "课堂管理", "教师成长"]}, "english_interview": {"name": "英语面试", "group": "教育与语言", "summary": "用英语讲述经历、职业动机与解决问题的过程。", "focus": "清晰表达与具体案例", "count": 20, "themes": ["Introduction", "Workplace communication", "Career motivation", "Problem solving"]}};
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
	function resumeInput() {
		const textArea = select('#resume-text');
		const done = select('#resume-done');
		const form = select('#practice-form');
		const status = select('#resume-completion');
		let composing = false;
		function finish() {
			const value = textArea.value.trim();
			textArea.blur();
			done.focus({ preventScroll: true });
			status.textContent = value ? '已填写简历文字，确认后上传。' : '可直接开始练习。';
		}
		textArea.addEventListener('compositionstart', () => { composing = true; });
		textArea.addEventListener('compositionend', () => { composing = false; });
		textArea.addEventListener('keydown', event => {
			if (event.key !== 'Enter' || event.isComposing || composing || event.keyCode === 229) return;
			if (!event.ctrlKey && !event.metaKey) return;
			event.preventDefault();
			finish();
		});
		textArea.addEventListener('input', () => { status.textContent = ''; });
		done.addEventListener('click', () => { if (!composing) finish(); });
		form.addEventListener('submit', () => {
			if (document.activeElement === textArea) textArea.blur();
		}, { capture: true });
	}
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
	function scoringEvidence() {
		const reasons = {
			depth: ['技术深度 · 覆盖了什么', '覆盖三个索引锚点；还没有解释磁盘 IO 与树高度的关系。下一问可以从这里展开。'],
			expression: ['表达逻辑 · 示例说明', '示例回答51字符，示例按回答长度估算为2.5分，不代表表达质量。'],
			match: ['岗位匹配 · 示例说明', '锚点覆盖率与回答长度加权为6.3分，不代表岗位胜任力。']
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
	[deviceHome, mobileHome, navigation, heroDemo, homepageCounts, questionDemo, revealSections, scoringEvidence, practiceForm, resumeInput, practicePreview, workspaceLinks, accountCarousel].forEach((initialize) => {
		try { initialize(); }
		catch { document.documentElement.classList.add('partial-interaction'); }
	});
})();
