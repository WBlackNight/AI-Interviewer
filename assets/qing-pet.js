/* Small cross-page launcher. React and chat requests load only after opening. */
(function () {
  'use strict';
/* Geometry only; stored values are viewport fractions, never account or chat data. */
function petPosition(saved, width, height, top = 76) {
  const maxX = Math.max(12, width - 88), maxY = Math.max(12, height - 104);
  const minY = Math.min(top, maxY);
  const clamp = (n, min, max) => Math.max(min, Math.min(max, n));
  const valid = saved && typeof saved.x === 'number' && Number.isFinite(saved.x) && typeof saved.y === 'number' && Number.isFinite(saved.y);
  return {x: valid ? clamp(saved.x, 0, 1) * (maxX - 12) + 12 : maxX,
    y: valid ? clamp(saved.y, 0, 1) * (maxY - minY) + minY : maxY, maxX, maxY, minY};
}
function petPanel(position, width, height) {
  const w = Math.min(420, Math.max(0, width - 24)), h = Math.min(640, Math.max(0, height - 108));
  const beside = width >= 760;
  const target = beside ? position.x > width / 2 ? position.x - w - 12 : position.x + 88 : position.x > width / 2 ? position.x + 76 - w : position.x;
  const left = Math.max(12, Math.min(width - w - 12, target));
  return {left, top: Math.max(12, Math.min(height - h - 12, beside ? position.y + 92 - h : position.y - h - 10)), width: w, height: h};
}

  if (document.getElementById('qing-pet')) return;
  const storageKey = 'qing:pet-position:v1';
  let saved = null, drag = null, suppressClick = false, opened = false, loading = null, closing = null, settling = null;
  try { saved = JSON.parse(localStorage.getItem(storageKey)); } catch { /* Default position. */ }
  const node = (tag, text, cls) => { const e = document.createElement(tag); if (text) e.textContent = text; if (cls) e.className = cls; return e; };
  const host = node('div', '', 'qing-pet'); host.id = 'qing-pet';
  const button = node('button', '', 'qing-pet-button'); button.type = 'button';
  button.setAttribute('aria-label', '打开小青助手，可拖动调整位置，方向键移动'); button.setAttribute('aria-expanded', 'false'); button.setAttribute('aria-controls', 'qing-widget-panel');
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); svg.setAttribute('viewBox', '0 0 96 96'); svg.setAttribute('aria-hidden', 'true');
  function shape(tag, attrs, parent = svg) { const e = document.createElementNS('http://www.w3.org/2000/svg', tag); for (const [key, value] of Object.entries(attrs)) e.setAttribute(key, value); parent.append(e); return e; }
  shape('ellipse', {cx:'48',cy:'88',rx:'25',ry:'4',fill:'#274e3920',class:'qing-pet-shadow'});
  const body = shape('g', {class:'qing-pet-character'});
  shape('ellipse', {cx:'34',cy:'80',rx:'10',ry:'6',fill:'#8dbba1'}, body); shape('ellipse', {cx:'62',cy:'80',rx:'10',ry:'6',fill:'#8dbba1'}, body);
  shape('circle', {cx:'14',cy:'54',r:'8',fill:'#cce5d5',stroke:'#91b79c'}, body); shape('circle', {cx:'82',cy:'54',r:'8',fill:'#cce5d5',stroke:'#91b79c'}, body);
  shape('rect', {x:'16',y:'29',width:'64',height:'50',rx:'23',fill:'#f8fffa',stroke:'#8db49a','stroke-width':'1.5'}, body);
  shape('path', {d:'M48 29V20M48 24C34 27 31 15 32 12c12 0 17 6 16 12ZM48 20c0-10 9-13 15-12 1 10-5 15-15 12Z',fill:'#91c7a1',stroke:'#4d8962','stroke-width':'1.4','stroke-linejoin':'round',class:'qing-pet-sprout'}, body);
  const eyes = shape('g', {class:'qing-pet-eyes'}, body); shape('ellipse', {cx:'36',cy:'51',rx:'3.3',ry:'4.5',fill:'#28533c'}, eyes); shape('ellipse', {cx:'60',cy:'51',rx:'3.3',ry:'4.5',fill:'#28533c'}, eyes);
  shape('path', {d:'M42 61q6 6 12 0',fill:'none',stroke:'#487c57','stroke-width':'2','stroke-linecap':'round'}, body);
  shape('ellipse', {cx:'27',cy:'60',rx:'5',ry:'3',fill:'#dbeccf'}, body); shape('ellipse', {cx:'69',cy:'60',rx:'5',ry:'3',fill:'#dbeccf'}, body);
  button.append(svg, node('span', '小青', 'qing-pet-name')); host.append(button, node('span', '拖动换个位置 · 点击聊聊', 'qing-pet-hint'));
  const panel = node('section', '', 'qing-widget-panel'); panel.id = 'qing-widget-panel'; panel.hidden = true; panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-label', '小青面试助手');
  const mount = node('div'); mount.id = 'qing-widget-root'; panel.append(mount); document.body.append(host, panel);
  let position;
  function viewport() { return {width: document.documentElement.clientWidth || innerWidth, height: window.visualViewport?.height || innerHeight}; }
  function layout() {
    const {width, height} = viewport(); position = petPosition(saved, width, height, width < 760 ? 132 : 76);
    host.style.left = position.x + 'px'; host.style.top = position.y + 'px';
    host.setAttribute('data-side', position.x < width / 2 ? 'left' : 'right');
    const rect = petPanel(position, width, height);
    for (const [key, value] of Object.entries(rect)) panel.style[key] = value + 'px';
  }
  function move(x, y, persist = false) {
    const {width, height} = viewport(), limits = petPosition(null, width, height, width < 760 ? 132 : 76);
    saved = {x: (Math.max(12, Math.min(limits.maxX, x)) - 12) / Math.max(1, limits.maxX - 12), y: (Math.max(limits.minY, Math.min(limits.maxY, y)) - limits.minY) / Math.max(1, limits.maxY - limits.minY)};
    layout(); if (persist) try {localStorage.setItem(storageKey, JSON.stringify(saved));} catch { /* Position still works in this page. */ }
  }
  const motionAllowed = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === false;
  function close() {
    if (!opened) return;
    opened = false; panel.inert = true; button.setAttribute('aria-expanded', 'false'); button.focus({preventScroll:true});
    if (!panel.animate || !motionAllowed()) {panel.hidden = true; return;}
    const transition = panel.animate([{opacity:1,transform:'none'}, {opacity:0,transform:'translateY(6px) scale(.985)'}], {duration:140,easing:'cubic-bezier(.4,0,1,1)'});
    closing = transition;
    transition.finished.then(() => {if (closing === transition && !opened) {panel.hidden = true; closing = null;}}, () => {});
  }
  function load() {
    if (loading) return loading;
    mount.replaceChildren(); const status = node('p', '正在唤醒小青…', 'qing-widget-loading'); status.setAttribute('role', 'status'); mount.append(status);
    loading = new Promise((resolve, reject) => {
      const script = document.createElement('script'); script.src = "/assets/qing-widget.js?v=3c45c0af995b";
      script.onload = resolve; script.onerror = () => {script.remove(); reject(new Error('load'));}; document.head.append(script);
    }).catch(() => {
      loading = null; const error = node('div', '', 'qing-widget-loading'); error.setAttribute('role', 'alert');
      error.append(node('p', '小青暂时没能打开，请再试一次。')); const retry = node('button', '重新打开'); retry.type = 'button'; retry.addEventListener('click', load);
      const link = node('a', '进入完整聊天页'); link.href = '/assistant'; error.append(retry, link); mount.replaceChildren(error);
    });
    return loading;
  }
  button.addEventListener('click', () => {
    if (suppressClick) {suppressClick = false; return;}
    if (location.pathname.replace(/\/$/, '') === '/assistant') {document.getElementById('qing-message')?.focus(); return;}
    if (opened) {close(); return;}
    closing?.cancel(); closing = null;
    opened = true; panel.hidden = false; panel.inert = false; button.setAttribute('aria-expanded', 'true');
    document.getElementById('qing-widget-message')?.focus({preventScroll:true}); void load();
  });
  button.addEventListener('pointerdown', event => {
    if (event.button !== 0 || drag) return;
    settling?.cancel(); settling = null;
    suppressClick = false;
    drag = {id:event.pointerId,x:event.clientX,y:event.clientY,left:position.x,top:position.y,moved:false}; button.setPointerCapture(event.pointerId);
  });
  button.addEventListener('pointermove', event => {
    if (!drag || drag.id !== event.pointerId) return;
    const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
    if (Math.hypot(dx,dy) < 6 && !drag.moved) return;
    drag.moved = true; host.classList.add('is-dragging'); move(drag.left + dx, drag.top + dy);
  });
  function endDrag(event) {
    if (!drag || event.pointerId !== drag.id) return;
    if (drag.moved) {
      suppressClick = true; const previousX = position.x;
      move(position.x < viewport().width / 2 ? 12 : position.maxX, position.y, true);
      if (host.animate && motionAllowed()) settling = host.animate([{transform:'translateX(' + (previousX - position.x) + 'px)'}, {transform:'translateX(0)'}], {duration:240,easing:'cubic-bezier(.22,1,.36,1)'});
    }
    drag = null; host.classList.remove('is-dragging');
  }
  for (const type of ['pointerup','pointercancel','lostpointercapture']) button.addEventListener(type, endDrag);
  button.addEventListener('keydown', event => {
    const directions = {ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}, direction = directions[event.key];
    if (direction) {event.preventDefault(); const step = event.shiftKey ? 32 : 16; move(position.x + direction[0] * step, position.y + direction[1] * step, true);}
    if (event.key === 'Escape' && opened) close();
    if (event.key === 'Enter' || event.key === ' ') suppressClick = false;
  });
  panel.addEventListener('keydown', event => {if (event.key === 'Escape') {event.preventDefault(); close();}});
  addEventListener('qing:close', close);
  addEventListener('qing:busy', event => host.classList.toggle('is-thinking', Boolean(event.detail)));
  function quiet() {host.classList.toggle('is-idle', Boolean(document.hidden));}
  document.addEventListener?.('visibilitychange', quiet); quiet();
  addEventListener('resize', layout); window.visualViewport?.addEventListener('resize', layout);
  addEventListener('pageshow', layout); layout();
})();
