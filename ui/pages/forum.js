(function () {
  'use strict';
/* @include session */
/* @include http */
/* @include notice */
  const root = document.querySelector('#forum-content');
  const params = new URLSearchParams(location.search);
  const emojis = ['🙂', '👍', '👏', '💡', '🎯', '💪', '🙏', '🎉', '🤔', '✨', '✅', '📌'];
  const states = { pending: '待审核', dismissed: '已驳回', actioned: '已下架' };
  const filters = { all: '全部', featured: '精华', mine: '我的帖子', saved: '我的收藏' };
  const limit = 12;
  const offset = key => Math.max(0, Math.min(10000, Number.parseInt(params.get(key), 10) || 0));
  const query = (params.get('q') || '').slice(0, 64).trim();
  const order = params.get('sort') === 'latest' ? 'latest' : 'rank';
  let context;

  function el(tag, value = '', cls = '') {
    const node = document.createElement(tag);
    if (value) node.textContent = value;
    if (cls) node.className = cls;
    return node;
  }
  function append(parent, ...children) { parent.append(...children); return parent; }
  function link(label, href, cls = '') {
    const node = el('a', label, cls);
    node.href = href;
    return node;
  }
  function button(label, handler) {
    const node = el('button', label, 'forum-button');
    node.type = 'button';
    if (handler) node.addEventListener('click', handler);
    return node;
  }
  function url(values = {}) {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(values)) if (value !== '' && value != null) search.set(key, value);
    return '/forum' + (search.size ? '?' + search : '');
  }
  function login() {
    return link('登录后参与', '/account?next=' + encodeURIComponent(location.pathname + location.search), 'forum-button forum-primary');
  }
  function setStatus(value) { document.querySelector('#forum-status').textContent = value; }
  function api(path, method = 'GET', data) {
    return requestJSON('/api/forum' + path, {
      auth: Boolean(readSession()) && (path === '/context' || Boolean(context?.viewer)), method,
      ...(data === undefined ? {} : { body: JSON.stringify(data), headers: { 'Content-Type': 'application/json' } }),
    });
  }
  function date(value) {
    return value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Shanghai' }).format(new Date(value)) : '';
  }
  function textMark(node, raw, keyword) {
    const pattern = keyword && new RegExp('(' + keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
    if (!pattern) { node.textContent = raw; return node; }
    raw.split(pattern).forEach((part, index) => node.append(index % 2 ? el('mark', part) : document.createTextNode(part)));
    return node;
  }
  function selectField(label, choices, initial) {
    const field = el('label', label, 'forum-field');
    const select = el('select');
    for (const [id, name] of Object.entries(choices)) {
      const option = el('option', name);
      option.value = id;
      select.append(option);
    }
    if (initial) select.value = initial;
    field.append(select);
    return { field, select };
  }
  function avatar(author) {
    const image = author.avatar_url && el('img', '', 'forum-avatar');
    if (image) {
      image.src = author.avatar_url;
      image.alt = '';
      image.loading = 'lazy';
      image.width = 36;
      image.height = 36;
      image.addEventListener('error', () => image.replaceWith(el('span', Array.from(author.nickname)[0], 'forum-avatar')));
      return image;
    }
    return el('span', Array.from(author.nickname)[0], 'forum-avatar');
  }
  function badge(code, highlight = '') {
    return textMark(el('span', '', 'forum-badge'), context.identities[code] || '社区成员', highlight);
  }
  function authorLine(author, identity, time, highlight = '', showHandle = false) {
    const row = el('div', '', 'forum-author');
    const who = link('', url({ user: author.id }), 'forum-person');
    who.append(avatar(author), textMark(el('strong'), author.nickname, highlight));
    row.append(who);
    if (showHandle && author.username !== author.nickname) {
      row.append(textMark(el('span', '', 'forum-handle'), '@' + author.username, highlight));
    }
    row.append(badge(identity, highlight));
    if (time) row.append(el('time', date(time), 'forum-time'));
    return row;
  }
  function postCard(post, highlight = '') {
    const card = el('article', '', 'forum-card forum-post');
    const title = textMark(link('', url({ post: post.id })), post.title, highlight);
    card.append(authorLine(post.author, post.identity, post.created_at, highlight, !!highlight),
      append(el('h3'), title), el('p', post.excerpt, 'forum-excerpt'));
    const meta = el('div', '', 'forum-meta');
    if (post.featured) meta.append(el('span', '精华', 'forum-featured'));
    meta.append(el('span', post.likes + ' 点赞'), el('span', post.comments + ' 回复'));
    card.append(meta);
    return card;
  }
  function empty(title, copy, action) {
    const panel = append(el('div', '', 'forum-empty'), el('h3', title), el('p', copy));
    if (action) panel.append(action);
    return panel;
  }
  function pager(next, key, urlValues) {
    const current = offset(key);
    if (!current && next == null) return el('div');
    const nav = el('nav', '', 'forum-pager');
    nav.setAttribute('aria-label', '列表分页');
    if (current) nav.append(link('上一页', url({ ...urlValues, [key]: Math.max(0, current - limit) }), 'forum-button'));
    if (next != null && next <= 10000) nav.append(link('下一页', url({ ...urlValues, [key]: next }), 'forum-button'));
    return nav;
  }
  function gate() {
    return empty('登录后参与社区', '你可以先浏览讨论。登录后发帖、回复、点赞、收藏和举报。', login());
  }
  function identityForm() {
    const form = el('form', '', 'forum-card forum-form');
    const options = { '': '请选择社区身份', ...context.identities };
    const { field, select } = selectField('社区身份', options, context.viewer.identity);
    select.required = true;
    form.append(el('h2', context.viewer.identity ? '修改社区身份' : '选择你的社区身份'),
      el('p', '选择后会公开显示社区主页、昵称、用户名和头像。新内容将使用当前身份。'),
      field, submitButton('保存身份'));
    wireForm(form, async () => {
      const result = await api('/identity', 'PUT', { identity: select.value });
      context.viewer.identity = result.identity;
      setStatus('社区身份已保存');
      await render();
    });
    return form;
  }
  function submitButton(label) {
    const node = button(label);
    node.type = 'submit';
    node.classList.add('forum-primary');
    return node;
  }
  function wireForm(form, action) {
    const feedback = el('p', '', 'forum-error');
    feedback.setAttribute('role', 'alert');
    form.append(feedback);
    let pending = false;
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (pending) return;
      pending = true;
      const submit = form.querySelector('button[type=submit]');
      submit.disabled = true;
      form.setAttribute('aria-busy', 'true');
      feedback.textContent = '';
      try { await action(); }
      catch (error) { feedback.textContent = error.message; }
      finally { pending = false; submit.disabled = false; form.removeAttribute('aria-busy'); }
    });
  }
  function field(label, type, max, required = true) {
    const wrapper = el('label', label, 'forum-field');
    const input = el(type === 'textarea' ? 'textarea' : 'input');
    if (type !== 'textarea') input.type = type;
    input.maxLength = max;
    input.required = required;
    return { field: append(wrapper, input), input };
  }
  function emojiPicker(input) {
    const details = el('details', '', 'forum-emojis');
    const options = el('div', '', 'forum-emoji-options');
    for (const emoji of emojis) {
      options.append(button(emoji, () => {
        if (input.value.length - (input.selectionEnd - input.selectionStart) + emoji.length > input.maxLength) return;
        input.setRangeText(emoji, input.selectionStart, input.selectionEnd, 'end');
        input.dispatchEvent(new Event('input', { bubbles: true }));
        details.open = false;
        input.focus();
      }));
    }
    return append(details, el('summary', '插入表情'), options);
  }
  function composer(post = null) {
    const form = el('form', '', 'forum-card forum-form');
    form.append(el('h2', post ? '写回复' : '发布帖子'), badge(context.viewer.identity));
    const title = !post && field('标题', 'text', 100);
    if (title) form.append(title.field);
    const body = field(post ? '回复内容' : '正文', 'textarea', post ? 1500 : 8000);
    body.input.rows = post ? 4 : 8;
    const count = el('small', '0 / ' + body.input.maxLength, 'forum-handle');
    body.input.addEventListener('input', () => { count.textContent = body.input.value.length + ' / ' + body.input.maxLength; });
    form.append(body.field, append(el('div', '', 'forum-compose-tools'), emojiPicker(body.input), count),
      submitButton(post ? '提交回复' : '发布帖子'));
    wireForm(form, async () => {
      if (post) {
        await api('/posts/' + post + '/comments', 'POST', { body: body.input.value });
        body.input.value = '';
        body.input.dispatchEvent(new Event('input'));
        await render();
        setStatus('回复已发布，按时间排在讨论末尾。');
        root.querySelector('#forum-replies')?.focus();
      } else {
        const result = await api('/posts', 'POST', { title: title.input.value, body: body.input.value });
        notify('帖子已发布', 'success', true);
        location.assign(url({ post: result.id }));
      }
    });
    return form;
  }
  function searchForm() {
    const form = el('form', '', 'forum-search');
    form.action = '/forum';
    form.method = 'get';
    const input = el('input');
    input.type = 'search';
    input.name = 'q';
    input.placeholder = '搜索标题、用户名或身份';
    input.setAttribute('aria-label', '搜索标题、用户名或身份');
    input.maxLength = 64;
    input.required = true;
    input.value = query;
    return append(form, input, submitButton('搜索'));
  }
  function feedNav(filter) {
    const nav = el('nav', '', 'forum-filters');
    nav.setAttribute('aria-label', '筛选帖子');
    for (const [value, label] of Object.entries(filters)) {
      const item = link(label, url({ filter: value, sort: order }), 'forum-button');
      if (filter === value) item.setAttribute('aria-current', 'page');
      nav.append(item);
    }
    const { field, select } = selectField('排序', { rank: '综合', latest: '最新' }, order);
    select.addEventListener('change', () => location.assign(url({ filter, sort: select.value })));
    return append(el('div', '', 'forum-toolbar'), nav, field);
  }
  function sidebar() {
    const aside = el('aside', '', 'forum-card forum-side');
    if (!context.viewer) return append(aside, el('h2', '加入讨论'), el('p', '登录后选择社区身份，再分享你的经历。'), login());
    aside.append(el('h2', '我的社区'));
    if (context.viewer.identity) {
      aside.append(badge(context.viewer.identity), link('我的社区主页', url({ user: context.viewer.id })),
        link('查看收藏', url({ filter: 'saved' })), link('修改身份', url({ view: 'identity' })));
    } else aside.append(link('选择社区身份', url({ view: 'identity' }), 'forum-button'));
    if (context.viewer.can_moderate) aside.append(link('举报审核', url({ view: 'moderation' })));
    return aside;
  }
  async function feed() {
    const filter = Object.hasOwn(filters, params.get('filter')) ? params.get('filter') : 'all';
    const list = el('div', '', 'forum-stack');
    list.append(searchForm(), feedNav(filter));
    if ((filter === 'mine' || filter === 'saved') && !context.viewer) list.append(gate());
    else {
      const result = await api('/posts?' + new URLSearchParams({ filter, sort: order, offset: offset('offset'), limit }));
      result.items.forEach(post => list.append(postCard(post)));
      if (!result.items.length) list.append(empty(
        filter === 'saved' ? '还没有收藏' : filter === 'featured' ? '暂无精华帖' : '这里还没有帖子',
        filter === 'featured' ? '获得 ' + context.featured_likes + ' 个点赞后会进入精华。' : '可以浏览其他讨论，或分享一段面试经历。',
        filter === 'saved' || filter === 'featured' ? link('浏览全部帖子', '/forum', 'forum-button') : link('发布帖子', url({ view: 'new' }), 'forum-button')
      ));
      list.append(pager(result.next_offset, 'offset', { filter, sort: order }));
    }
    return append(el('div', '', 'forum-grid'), list, sidebar());
  }
  async function searchResults() {
    const args = { q: query, post_offset: offset('post_offset'), user_offset: offset('user_offset'), limit };
    const result = await api('/search?' + new URLSearchParams(args));
    const content = append(el('div', '', 'forum-stack'), searchForm(), el('h2', '搜索结果'));
    const people = append(el('section', '', 'forum-card forum-stack'), el('h3', '用户'));
    result.users.items.forEach(user => people.append(authorLine(user, user.identity, null, query, true)));
    if (!result.users.items.length) people.append(el('p', '没有匹配的社区用户。'));
    people.append(pager(result.users.next_offset, 'user_offset', { q: query, post_offset: args.post_offset }));
    const posts = append(el('section', '', 'forum-stack'), el('h3', '帖子'));
    result.posts.items.forEach(post => posts.append(postCard(post, query)));
    if (!result.posts.items.length) posts.append(empty('没有匹配的帖子', '试试缩短关键词，或搜索身份名称。'));
    posts.append(pager(result.posts.next_offset, 'post_offset', { q: query, user_offset: args.user_offset }));
    return append(content, people, posts);
  }
  function reportDialog(path, trigger) {
    const dialog = el('dialog', '', 'forum-dialog');
    dialog.setAttribute('aria-label', '举报内容');
    const form = el('form', '', 'forum-form');
    const reason = selectField('举报原因', context.report_reasons);
    const note = field('补充说明（选填）', 'textarea', 300, false);
    note.input.rows = 3;
    form.append(el('h2', '举报内容'), reason.field, note.field,
      append(el('div', '', 'forum-actions'), button('取消', () => dialog.close()), submitButton('提交举报')));
    wireForm(form, async () => {
      const result = await api(path, 'POST', { reason: reason.select.value, note: note.input.value });
      dialog.close();
      setStatus(result.duplicate ? '你已举报过这条内容。' : '举报已提交，等待审核。');
      notify(result.duplicate ? '你已举报过这条内容' : '举报已提交');
    });
    dialog.addEventListener('close', () => { dialog.remove(); trigger.focus(); });
    root.append(append(dialog, form));
    dialog.showModal();
  }
  function postActions(post, card) {
    const base = '/posts/' + post.id;
    const likes = button('');
    const saved = button('');
    const featured = el('span', '精华', 'forum-featured');
    function update() {
      likes.textContent = (post.liked ? '已点赞' : '点赞') + ' ' + post.likes;
      likes.setAttribute('aria-pressed', String(post.liked));
      saved.textContent = post.saved ? '已收藏' : '收藏';
      saved.setAttribute('aria-pressed', String(post.saved));
      featured.hidden = !post.featured;
    }
    for (const [node, key, route] of [[likes, 'liked', 'like'], [saved, 'saved', 'bookmark']]) {
      node.addEventListener('click', async () => {
        likes.disabled = saved.disabled = true;
        try {
          const result = await api(base + '/' + route, post[key] ? 'DELETE' : 'PUT');
          Object.assign(post, result);
          update();
          setStatus(node.textContent);
        } catch (error) { notify(error.message, 'error'); }
        finally { likes.disabled = saved.disabled = false; }
      });
    }
    const report = button('举报帖子', () => reportDialog(base + '/reports', report));
    update();
    card.append(append(el('div', '', 'forum-actions'), featured, likes, saved, report));
  }
  async function detail(postId) {
    const [post, replies] = await Promise.all([api('/posts/' + postId),
      api('/posts/' + postId + '/comments?' + new URLSearchParams({ offset: offset('offset'), limit }))]);
    const card = append(el('article', '', 'forum-card forum-detail'), authorLine(post.author, post.identity, post.created_at),
      el('h2', post.title), el('p', post.body, 'forum-body'));
    if (context.viewer) postActions(post, card);
    else card.append(append(el('div', '', 'forum-meta'), post.featured ? el('span', '精华', 'forum-featured') : '',
      el('span', post.likes + ' 点赞'), login()));
    const title = el('h2', '回复 · ' + post.comments);
    title.id = 'forum-replies';
    title.tabIndex = -1;
    const section = append(el('section', '', 'forum-stack'), title);
    for (const reply of replies.items) {
      const row = append(el('article', '', 'forum-card forum-reply'), authorLine(reply.author, reply.identity, reply.created_at), el('p', reply.body, 'forum-body'));
      if (context.viewer) {
        const report = button('举报回复', () => reportDialog('/posts/' + postId + '/comments/' + reply.id + '/reports', report));
        row.append(report);
      }
      section.append(row);
    }
    if (!replies.items.length) section.append(empty('还没有回复', '可以从补充一个观点或追问开始。'));
    section.append(pager(replies.next_offset, 'offset', { post: postId }));
    section.append(!context.viewer ? gate() : context.viewer.identity ? composer(postId) : identityForm());
    return append(el('div', '', 'forum-stack'), card, section);
  }
  async function profile(userId) {
    const [info, posts] = await Promise.all([api('/users/' + userId),
      api('/users/' + userId + '/posts?' + new URLSearchParams({ offset: offset('offset'), limit }))]);
    const profile = append(el('section', '', 'forum-card forum-stack'),
      el('h2', info.nickname + '的社区主页'), authorLine(info, info.identity, null, '', true),
      append(el('div', '', 'forum-meta'), el('span', '发帖 ' + info.post_count), el('span', '收藏 ' + info.saved_count)));
    if (info.is_self) profile.append(append(el('div', '', 'forum-actions'),
      link('编辑资料', '/account?view=profile', 'forum-button'), link('修改身份', url({ view: 'identity' }), 'forum-button'),
      link('查看收藏', url({ filter: 'saved' }), 'forum-button')));
    const list = append(el('section', '', 'forum-stack'), el('h2', '最近发布'));
    posts.items.forEach(post => list.append(postCard(post)));
    if (!posts.items.length) list.append(empty('还没有发布帖子', '该用户发布的讨论会显示在这里。'));
    return append(el('div', '', 'forum-stack'), profile, list, pager(posts.next_offset, 'offset', { user: userId }));
  }
  async function moderation() {
    if (!context.viewer) return gate();
    if (!context.viewer.can_moderate) return empty('需要管理员权限', '此页面供管理员处理举报。', link('返回社区', '/forum'));
    const state = Object.hasOwn(states, params.get('status')) ? params.get('status') : 'pending';
    const result = await api('/moderation/reports?' + new URLSearchParams({ status: state, offset: offset('offset'), limit }));
    const toolbar = selectField('记录状态', states, state);
    toolbar.select.addEventListener('change', () => location.assign(url({ view: 'moderation', status: toolbar.select.value })));
    const content = append(el('div', '', 'forum-stack'), el('h2', '举报审核'), toolbar.field);
    for (const row of result.items) {
      const card = append(el('article', '', 'forum-card forum-stack'),
        el('h3', row.title), el('p', states[row.status] + ' · ' + (row.target_kind === 'post' ? '帖子' : '回复') + ' · ' + date(row.created_at)),
        el('p', row.excerpt, 'forum-body'), el('p', '举报原因：' + context.report_reasons[row.reason]),
        el('p', row.note || '举报人未补充说明。'));
      const full = el('details');
      const fullBody = el('p', '', 'forum-body');
      const loadFull = button('读取完整内容', async () => {
        loadFull.disabled = true;
        try {
          fullBody.textContent = (await api('/moderation/reports/' + row.id)).body;
          loadFull.hidden = true;
        } catch (error) { fullBody.textContent = error.message; }
        finally { loadFull.disabled = false; }
      });
      card.append(append(full, el('summary', '查看完整内容'), loadFull, fullBody));
      if (state === 'pending') {
        const form = el('form', '', 'forum-form');
        const choice = selectField('处理决定', { dismiss: '驳回举报', hide: '下架被举报内容' });
        const note = field('审核说明', 'textarea', 300);
        note.input.rows = 3;
        form.append(choice.field, note.field, submitButton('提交审核决定'));
        wireForm(form, async () => {
          await api('/moderation/reports/' + row.id, 'PATCH', { decision: choice.select.value, note: note.input.value });
          await render();
          setStatus('审核结果已保存');
        });
        card.append(form);
      } else card.append(el('p', '审核说明：' + row.review_note), el('p', date(row.reviewed_at), 'forum-time'));
      content.append(card);
    }
    if (!result.items.length) content.append(empty('暂无此状态的举报', '可以切换状态查看其他记录。'));
    content.append(pager(result.next_offset, 'offset', { view: 'moderation', status: state }));
    return content;
  }
  async function render() {
    let view;
    try {
      if (params.get('view') === 'new') view = !context.viewer ? gate() : context.viewer.identity ? composer() : identityForm();
      else if (params.get('view') === 'identity') view = context.viewer ? identityForm() : gate();
      else if (params.get('view') === 'moderation') view = await moderation();
      else if (params.has('post')) view = await detail(encodeURIComponent(params.get('post')));
      else if (params.has('user')) view = await profile(encodeURIComponent(params.get('user')));
      else if (query) view = await searchResults();
      else view = await feed();
      if (params.has('view') || params.has('user') || params.has('post') || query) {
        view = append(el('div', '', 'forum-stack'), link('返回社区', '/forum', 'forum-back'), view);
      }
      root.replaceChildren(view);
    } catch (error) {
      root.replaceChildren(empty('暂时无法显示这部分内容', error.message,
        error.status === 401 ? login() : link('返回社区', '/forum', 'forum-button')));
    }
  }
  async function init() {
    try {
      context = await api('/context');
      await render();
    } catch (error) {
      root.replaceChildren(empty('暂时无法连接社区', error.message,
        error.status === 401 ? login() : button('重试', init)));
    }
  }
  addEventListener('account:changed', () => location.reload());
  addEventListener('account:expired', () => location.reload());
  void init();
})();
