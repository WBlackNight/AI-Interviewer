(() => {
  'use strict';
/* @include session */

  const find = id => document.getElementById(id);
  const dialog = find('onboarding');
  if (!dialog || typeof dialog.showModal !== 'function') return;

  const page = dialog.dataset.tourPage;
  const home = page === 'home';
  const steps = JSON.parse(dialog.dataset.tourSteps);
  const preference = home ? 'qingzhan:onboarding:v1' : 'qingzhan:guide:' + page + ':v1';
  const launcher = find('tour-open');
  const hint = find('tour-hint');
  const back = find('tour-back');
  const next = find('tour-next');
  const finish = find('tour-finish');
  let index = 0;
  let startingPractice = false;

  function isNew() {
    try { return !localStorage.getItem(preference); }
    catch { return false; }
  }

  function refreshHint() {
    if (hint) hint.hidden = !isNew();
  }

  function showStep() {
    const [title, copy] = steps[index];
    find('tour-meter').value = index + 1;
    find('tour-progress').textContent = '第 ' + (index + 1) + ' 步，共 ' + steps.length + ' 步';
    find('tour-step').textContent = title;
    find('tour-copy').textContent = copy;
    back.hidden = index === 0;
    next.hidden = index === steps.length - 1;
    finish.hidden = !next.hidden;
  }

  function openTour() {
    if (dialog.open) return;
    index = 0;
    startingPractice = false;
    showStep();
    dialog.showModal();
  }

  launcher.hidden = false;
  refreshHint();
  launcher.addEventListener('click', openTour);
  find('tour-skip').addEventListener('click', () => dialog.close());
  next.addEventListener('click', () => {
    index += 1;
    showStep();
    if (next.hidden) finish.focus();
  });
  back.addEventListener('click', () => {
    index -= 1;
    showStep();
    if (back.hidden) next.focus();
  });
  finish.addEventListener('click', () => {
    startingPractice = home;
    dialog.close();
  });
  dialog.addEventListener('close', () => {
    if (hint) hint.hidden = true;
    try { localStorage.setItem(preference, 'seen'); } catch { /* Preference may be unavailable. */ }
    (startingPractice ? find('cta-title') : launcher)?.focus({ preventScroll: true });
  });
  addEventListener('pageshow', refreshHint);

  const url = new URL(location.href);
  if (url.searchParams.get('tour') === '1') {
    url.searchParams.delete('tour');
    history.replaceState(history.state, '', url.href);
    openTour();
  } else if (home && !url.search && !url.hash && !readSession() && isNew()) {
    openTour();
  }
})();
