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
