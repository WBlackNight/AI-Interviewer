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
