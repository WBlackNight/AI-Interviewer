import React from 'react';

// Small safe Markdown subset: React text nodes only, no HTML or model-supplied links.
function inline(text: string) {
  return text
    .split(/(\*\*[^*\n]+\*\*|`[^`\n]+`)/g)
    .map((part, index) =>
      part.startsWith('**') && part.endsWith('**') ? (
        <strong key={index}>{part.slice(2, -2)}</strong>
      ) : part.startsWith('`') && part.endsWith('`') ? (
        <code key={index}>{part.slice(1, -1)}</code>
      ) : (
        part
      )
    );
}

export function AnswerText({ text }: { text: string }) {
  const blocks: React.ReactNode[] = [];
  const lines = text.split('\n');
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (line.startsWith('```')) {
      const start = index++;
      const code = [];
      while (index < lines.length && !lines[index].startsWith('```')) code.push(lines[index++]);
      if (index < lines.length) index++;
      blocks.push(
        <pre key={start}>
          <code>{code.join('\n')}</code>
        </pre>
      );
    } else if (/^#{1,4}\s/.test(line)) {
      blocks.push(<h3 key={index}>{inline(line.replace(/^#{1,4}\s+/, ''))}</h3>);
      index++;
    } else if (/^(?:[-*]\s|\d+[.)、]\s*)/.test(line)) {
      const start = index,
        items = [];
      while (index < lines.length && /^(?:[-*]\s|\d+[.)、]\s*)/.test(lines[index])) {
        items.push(
          <li key={index}>{inline(lines[index++].replace(/^(?:[-*]\s|\d+[.)、]\s*)/, ''))}</li>
        );
      }
      blocks.push(<ul key={start}>{items}</ul>);
    } else if (line.trim()) {
      blocks.push(<p key={index}>{inline(line)}</p>);
      index++;
    } else index++;
  }
  return <div className="qing-answer-text">{blocks}</div>;
}
