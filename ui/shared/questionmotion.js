  function renderQuestionTitle(node, text, turnId) {
    if (node.dataset.motionTurn === turnId && node.textContent === text) return;
    if (!turnId) {
      delete node.dataset.motionTurn;
      node.textContent = text;
      return;
    }
    node.dataset.motionTurn = turnId;
    const title = document.createElement('span');
    title.className = 'motion-question';
    title.textContent = text;
    node.replaceChildren(title);
  }
