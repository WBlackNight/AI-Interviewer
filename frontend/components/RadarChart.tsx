"use client";

/** 纯 SVG 雷达图（零依赖，数据来自后端 dimensions 聚合）。 */

interface RadarPoint {
  label: string;
  value: number; // 0-10
}

export default function RadarChart({
  points,
  size = 320,
}: {
  points: RadarPoint[];
  size?: number;
}) {
  if (points.length < 3) {
    return (
      <p className="text-sm text-slate-500">维度数据不足，无法绘制雷达图</p>
    );
  }

  const center = size / 2;
  const radius = size / 2 - 48; // 留出标签空间
  const angle = (i: number) => (Math.PI * 2 * i) / points.length - Math.PI / 2;

  const pointAt = (i: number, ratio: number) => {
    const r = radius * ratio;
    return [center + r * Math.cos(angle(i)), center + r * Math.sin(angle(i))];
  };

  const rings = [0.25, 0.5, 0.75, 1];
  const polygonFor = (ratio: (i: number) => number) =>
    points
      .map((_, i) => {
        const [x, y] = pointAt(i, ratio(i));
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");

  const dataRatio = (i: number) => Math.min(points[i].value, 10) / 10;

  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      className="mx-auto w-full max-w-sm"
      role="img"
      aria-label="能力维度雷达图"
    >
      {/* 网格环 */}
      {rings.map((ring) => (
        <polygon
          key={ring}
          points={polygonFor(() => ring)}
          fill="none"
          stroke="#E2E8F0"
          strokeWidth={1}
        />
      ))}
      {/* 轴线与标签 */}
      {points.map((point, i) => {
        const [x, y] = pointAt(i, 1);
        const [lx, ly] = pointAt(i, 1.18);
        return (
          <g key={point.label}>
            <line
              x1={center}
              y1={center}
              x2={x}
              y2={y}
              stroke="#E2E8F0"
              strokeWidth={1}
            />
            <text
              x={lx}
              y={ly}
              textAnchor="middle"
              dominantBaseline="central"
              className="fill-slate-600"
              fontSize={12}
            >
              {point.label}
            </text>
          </g>
        );
      })}
      {/* 数据面 */}
      <polygon
        points={polygonFor(dataRatio)}
        fill="rgba(40, 102, 72, 0.14)"
        stroke="#286648"
        strokeWidth={2}
      />
      {/* 数据点 */}
      {points.map((point, i) => {
        const [x, y] = pointAt(i, dataRatio(i));
        return <circle key={point.label} cx={x} cy={y} r={3.5} fill="#286648" />;
      })}
      {/* 数值 */}
      {points.map((point, i) => {
        const [x, y] = pointAt(i, Math.max(dataRatio(i) + 0.12, 0.15));
        return (
          <text
            key={`v-${point.label}`}
            x={x}
            y={y}
            textAnchor="middle"
            dominantBaseline="central"
            className="fill-brand-800"
            fontSize={11}
            fontWeight={600}
          >
            {point.value.toFixed(1)}
          </text>
        );
      })}
    </svg>
  );
}
