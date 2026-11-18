// Only public practice configuration belongs in the address. Never persist resume or identity.
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
