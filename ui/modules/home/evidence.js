  // 评分：同步原文、雷达与口径。
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
