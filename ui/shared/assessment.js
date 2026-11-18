  function renderAssessment(report, find) {
    const assessment = report.assessment;
    find('assessment').hidden = !assessment;
    if (!assessment) return;
    find('assessment-summary').textContent = assessment.summary + (report.is_complete ? '' : ' 当前为已提交回答的阶段反馈。');
    const strengths = find('strengths'), priorities = find('priorities');
    strengths.replaceChildren(); priorities.replaceChildren();
    for (const item of assessment.strengths) strengths.append(createNode('li', item.theme + ' · ' + item.point));
    if (!assessment.strengths.length) strengths.append(createNode('li', report.answer_count ? '继续补充完整回答，积累可复盘的表现。' : '完成一轮回答后，在这里回看已覆盖的要点。'));
    for (const item of assessment.priorities) priorities.append(createNode('li', item.theme + ' · ' + item.action));
    if (!assessment.priorities.length) priorities.append(createNode('li', report.answer_count ? '尝试变化场景，检查自己能否解释边界和取舍。' : '开始回答后生成具体建议。'));
  }
