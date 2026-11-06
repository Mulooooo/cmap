import { fmt } from "../format";

interface Props {
  points: [number, number][]; // [temps_s, meilleur coût]
  bks: number | null;
}

/** Courbe de convergence en escalier (SVG, sans dépendance). */
export default function Chart({ points, bks }: Props) {
  if (points.length < 2) return <div className="chart" />;
  const W = 760, H = 260, L = 56, R = 16, T = 14, B = 36;
  const xmax = Math.max(...points.map((p) => p[0])) || 1;
  const costs = points.map((p) => p[1]);
  let ymin = Math.min(...costs, bks ?? Infinity);
  let ymax = Math.max(...costs);
  const pad = (ymax - ymin) * 0.08 || 1;
  ymin -= pad;
  ymax += pad;
  const X = (x: number) => L + (x / xmax) * (W - L - R);
  const Y = (y: number) => T + (1 - (y - ymin) / (ymax - ymin)) * (H - T - B);

  let d = `M${X(points[0][0])},${Y(points[0][1])}`;
  for (let i = 1; i < points.length; i++) d += ` H${X(points[i][0])} V${Y(points[i][1])}`;
  const ticks = [0, 1, 2, 3, 4];

  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Meilleur coût en fonction du temps de calcul">
        {ticks.map((i) => {
          const y = ymin + (i / 4) * (ymax - ymin);
          const x = (i / 4) * xmax;
          return (
            <g key={i}>
              <line x1={L} x2={W - R} y1={Y(y)} y2={Y(y)} stroke="currentColor" strokeOpacity={0.12} />
              <text x={L - 8} y={Y(y) + 4} textAnchor="end">{fmt(Math.round(y))}</text>
              <text x={X(x)} y={H - 14} textAnchor="middle">{fmt(Math.round(x * 10) / 10)} s</text>
            </g>
          );
        })}
        {bks !== null && (
          <>
            <line x1={L} x2={W - R} y1={Y(bks)} y2={Y(bks)} stroke="#2ca02c" strokeDasharray="5 4" />
            <text x={W - R} y={Y(bks) - 5} textAnchor="end" fill="#2ca02c">
              Meilleure connue : {fmt(bks)}
            </text>
          </>
        )}
        <path d={d} fill="none" stroke="#2563eb" strokeWidth={2} />
      </svg>
    </div>
  );
}
