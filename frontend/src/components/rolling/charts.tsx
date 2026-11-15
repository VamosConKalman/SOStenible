// Primitives SVG petites i interactives per al dashboard de Rolling Horizon.
// Sense dependències: escala lineal, línies trencades per null, crosshair amb
// tooltip, línies clicables amb zona de clic ampla, mapa de calor i barres.
import { useMemo, useRef, useState, type ReactNode } from "react";
import { C } from "../../theme";

export type Pt = [number, number | null];

export interface Series {
  id: string;
  label: string;
  pts: Pt[];
  color: string;
  width?: number;
  dash?: string;
  opacity?: number;
  /** clicable: la línia té una zona de clic invisible de 10 px */
  onClick?: () => void;
  /** surt al tooltip del crosshair */
  tooltip?: boolean;
  /** surt a la llegenda */
  legend?: boolean;
  fmt?: (v: number) => string;
}

export interface Band { x0: number; x1: number; fill: string; label?: string }

interface LineChartProps {
  series: Series[];
  height?: number;
  xMin: number; xMax: number;
  yMin?: number; yMax?: number;
  xTicks?: number[];
  xFmt?: (x: number) => string;
  yFmt?: (y: number) => string;
  yLabel?: string;
  bands?: Band[];
  vline?: number | null;
  hline?: number | null;
  onHoverSeries?: (id: string | null) => void;
  onClickX?: (x: number) => void;
  ariaLabel: string;
}

const W = 760;
const M = { l: 74, r: 14, t: 12, b: 26 };

function niceTicks(lo: number, hi: number, n = 5) {
  const span = Math.max(1e-9, hi - lo);
  const step0 = span / n;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((f) => f * mag).find((s) => s >= step0) ?? step0;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}

function pathOf(pts: Pt[], sx: (x: number) => number, sy: (y: number) => number) {
  let d = "", pen = false;
  for (const [x, y] of pts) {
    if (y === null || !Number.isFinite(y)) { pen = false; continue; }
    d += `${pen ? "L" : "M"}${sx(x).toFixed(1)} ${sy(y).toFixed(1)}`;
    pen = true;
  }
  return d;
}

export function LineChart(p: LineChartProps) {
  const H = p.height ?? 260;
  const [hx, setHx] = useState<number | null>(null);
  const ref = useRef<SVGSVGElement>(null);

  const [yMin, yMax] = useMemo(() => {
    if (p.yMin !== undefined && p.yMax !== undefined) return [p.yMin, p.yMax];
    let lo = Infinity, hi = -Infinity;
    for (const s of p.series) for (const [, y] of s.pts) if (y !== null && Number.isFinite(y)) { lo = Math.min(lo, y); hi = Math.max(hi, y); }
    if (!Number.isFinite(lo)) { lo = 0; hi = 1; }
    if (p.hline !== undefined && p.hline !== null) { lo = Math.min(lo, p.hline); hi = Math.max(hi, p.hline); }
    const pad = (hi - lo) * 0.06 || 1;
    return [p.yMin ?? lo - pad, p.yMax ?? hi + pad];
  }, [p.series, p.yMin, p.yMax, p.hline]);

  const sx = (x: number) => M.l + ((x - p.xMin) / Math.max(1e-9, p.xMax - p.xMin)) * (W - M.l - M.r);
  const sy = (y: number) => M.t + (1 - (y - yMin) / Math.max(1e-9, yMax - yMin)) * (H - M.t - M.b);
  const yt = niceTicks(yMin, yMax, 4);
  const xt = p.xTicks ?? niceTicks(p.xMin, p.xMax, 8);
  const xf = p.xFmt ?? ((x: number) => String(x));
  const yf = p.yFmt ?? ((y: number) => String(Math.round(y)));

  const toX = (clientX: number) => {
    const el = ref.current;
    if (!el) return null;
    const r = el.getBoundingClientRect();
    const vx = ((clientX - r.left) / r.width) * W;
    const x = p.xMin + ((vx - M.l) / (W - M.l - M.r)) * (p.xMax - p.xMin);
    return Math.max(p.xMin, Math.min(p.xMax, Math.round(x)));
  };

  const tipRows = hx === null ? [] : p.series.filter((s) => s.tooltip).map((s) => {
    const pt = s.pts.find(([x]) => x === hx);
    return { s, v: pt ? pt[1] : null };
  }).filter((r) => r.v !== null && Number.isFinite(r.v as number));

  const legend = p.series.filter((s) => s.legend);

  return (
    <div className="rh-chart">
      {legend.length > 0 && (
        <ul className="legend">
          {legend.map((s) => (
            <li key={s.id}>
              <svg width="22" height="10" aria-hidden><line x1="1" y1="5" x2="21" y2="5" stroke={s.color} strokeWidth={Math.max(2, s.width ?? 2)} strokeDasharray={s.dash} /></svg>
              {s.label}
            </li>
          ))}
        </ul>
      )}
      <div className="rh-chart-box">
        <svg ref={ref} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={p.ariaLabel}
          onMouseMove={(e) => setHx(toX(e.clientX))} onMouseLeave={() => { setHx(null); p.onHoverSeries?.(null); }}
          onClick={(e) => { const x = toX(e.clientX); if (x !== null) p.onClickX?.(x); }}
          style={{ width: "100%", height: "auto", display: "block", cursor: p.onClickX ? "pointer" : "default" }}>
          {(p.bands ?? []).map((b, i) => (
            <g key={i}>
              <rect x={sx(b.x0)} y={M.t} width={Math.max(0, sx(b.x1) - sx(b.x0))} height={H - M.t - M.b} fill={b.fill} />
              {b.label && <text x={sx(b.x0) + 6} y={M.t + 13} className="rh-band-txt">{b.label}</text>}
            </g>
          ))}
          {yt.map((v) => (
            <g key={v}>
              <line x1={M.l} x2={W - M.r} y1={sy(v)} y2={sy(v)} stroke={C.grid} strokeWidth={1} />
              <text x={M.l - 6} y={sy(v) + 4} textAnchor="end" className="rh-axis">{yf(v)}</text>
            </g>
          ))}
          {xt.map((v) => (
            <text key={v} x={sx(v)} y={H - 8} textAnchor="middle" className="rh-axis">{xf(v)}</text>
          ))}
          {p.yLabel && <text x={8} y={M.t + 2} className="rh-axis" transform={`rotate(-90 8 ${M.t + 2})`} textAnchor="end">{p.yLabel}</text>}
          {p.hline !== undefined && p.hline !== null && (
            <line x1={M.l} x2={W - M.r} y1={sy(p.hline)} y2={sy(p.hline)} stroke={C.ink2} strokeWidth={1} />
          )}

          {p.series.map((s) => {
            const d = pathOf(s.pts, sx, sy);
            if (!d) return null;
            return (
              <g key={s.id}>
                <path d={d} fill="none" stroke={s.color} strokeWidth={s.width ?? 2} strokeDasharray={s.dash}
                  opacity={s.opacity ?? 1} strokeLinejoin="round" strokeLinecap="round" pointerEvents="none" />
                {s.onClick && (
                  <path d={d} fill="none" stroke="transparent" strokeWidth={10} style={{ cursor: "pointer" }}
                    onMouseEnter={() => p.onHoverSeries?.(s.id)}
                    onClick={(e) => { e.stopPropagation(); s.onClick?.(); }}>
                    <title>{s.label}</title>
                  </path>
                )}
              </g>
            );
          })}

          {p.vline !== undefined && p.vline !== null && (
            <line x1={sx(p.vline)} x2={sx(p.vline)} y1={M.t} y2={H - M.b} stroke={C.ink} strokeWidth={1.5} strokeDasharray="3 3" pointerEvents="none" />
          )}
          {hx !== null && (
            <g pointerEvents="none">
              <line x1={sx(hx)} x2={sx(hx)} y1={M.t} y2={H - M.b} stroke={C.muted} strokeWidth={1} />
              {tipRows.map(({ s, v }) => (
                <circle key={s.id} cx={sx(hx)} cy={sy(v as number)} r={4} fill={s.color} stroke="#fff" strokeWidth={2} />
              ))}
            </g>
          )}
        </svg>
        {hx !== null && tipRows.length > 0 && (
          <div className="tip rh-tip" style={{ left: `${(sx(hx) / W) * 100}%` }}>
            <b>{xf(hx)}</b>
            {tipRows.map(({ s, v }) => (
              <span key={s.id}><i style={{ background: s.color }} />{s.label}: <b>{(s.fmt ?? yf)(v as number)}</b></span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mapa de calor: files = hora de decisió t, columnes = hora objectiu t+k.
// ---------------------------------------------------------------------------

interface HeatmapProps {
  rows: number;
  cols: number;
  value: (r: number, c: number) => number | null;
  vmax: number;
  selectedRow: number | null;
  onSelectRow: (r: number) => void;
  rowFmt: (r: number) => string;
  colFmt: (c: number) => string;
  cellTip: (r: number, c: number, v: number) => ReactNode;
  dayEnd?: number;
  ariaLabel: string;
}

/** Divergent: càrrega (lila) ↔ 0 (gris clar) ↔ descàrrega (verd). */
export function divColor(v: number, vmax: number) {
  const t = Math.max(-1, Math.min(1, v / Math.max(1e-9, vmax)));
  const mix = (a: string, b: string, k: number) => {
    const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
    const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
    return `rgb(${pa.map((x, i) => Math.round(x + (pb[i] - x) * k)).join(",")})`;
  };
  const mid = "#EEEDE8";
  return t >= 0 ? mix(mid, C.charge, Math.sqrt(t)) : mix(mid, C.battery, Math.sqrt(-t));
}

export function Heatmap(p: HeatmapProps) {
  const cw = 15, ch = 13, ml = 46, mt = 18;
  const Wd = ml + p.cols * cw + 4, Hd = mt + p.rows * ch + 4;
  const [hov, setHov] = useState<[number, number] | null>(null);
  const hv = hov ? p.value(hov[0], hov[1]) : null;
  return (
    <div className="rh-chart-box">
      <svg viewBox={`0 0 ${Wd} ${Hd}`} role="img" aria-label={p.ariaLabel} style={{ width: "100%", height: "auto", display: "block" }}
        onMouseLeave={() => setHov(null)}>
        {[...Array(p.cols).keys()].filter((c) => c % 3 === 0).map((c) => (
          <text key={c} x={ml + c * cw + cw / 2} y={12} textAnchor="middle" className="rh-axis">{p.colFmt(c)}</text>
        ))}
        {[...Array(p.rows).keys()].map((r) => (
          <g key={r}>
            <text x={ml - 6} y={mt + r * ch + ch - 3} textAnchor="end" className="rh-axis"
              style={{ fontWeight: r === p.selectedRow ? 700 : 400, cursor: "pointer" }} onClick={() => p.onSelectRow(r)}>
              {p.rowFmt(r)}
            </text>
            {[...Array(p.cols).keys()].map((c) => {
              const v = p.value(r, c);
              if (v === null) return null;
              return (
                <rect key={c} x={ml + c * cw + 1} y={mt + r * ch + 1} width={cw - 2} height={ch - 2} rx={2}
                  fill={divColor(v, p.vmax)} style={{ cursor: "pointer" }}
                  stroke={c === r ? C.ink : "none"} strokeWidth={c === r ? 1.2 : 0}
                  onMouseEnter={() => setHov([r, c])} onClick={() => p.onSelectRow(r)} />
              );
            })}
          </g>
        ))}
        {p.selectedRow !== null && (
          <rect x={ml - 1} y={mt + p.selectedRow * ch} width={p.cols * cw + 2} height={ch} fill="none" stroke={C.ink} strokeWidth={2} rx={3} pointerEvents="none" />
        )}
        {p.dayEnd !== undefined && (
          <line x1={ml + p.dayEnd * cw} x2={ml + p.dayEnd * cw} y1={mt - 4} y2={Hd} stroke={C.ink2} strokeDasharray="3 3" />
        )}
      </svg>
      {hov && hv !== null && (
        <div className="tip rh-tip" style={{ left: `${((ml + hov[1] * cw) / Wd) * 100}%`, top: `${((mt + hov[0] * ch) / Hd) * 100}%` }}>
          {p.cellTip(hov[0], hov[1], hv)}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Barres verticals amb zero (positives i negatives), amb tooltip.
// ---------------------------------------------------------------------------

export function Bars({ values, labels, color, negColor, height = 150, fmt, ariaLabel, selected, onSelect }: {
  values: (number | null)[]; labels: string[]; color: string; negColor?: string; height?: number;
  fmt: (v: number) => string; ariaLabel: string; selected?: number | null; onSelect?: (i: number) => void;
}) {
  const [hov, setHov] = useState<number | null>(null);
  const vals = values.map((v) => (v === null || !Number.isFinite(v) ? 0 : v));
  const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals, 1e-9);
  const n = values.length;
  const bw = (W - M.l - M.r) / Math.max(1, n);
  const sy = (y: number) => M.t + (1 - (y - lo) / Math.max(1e-9, hi - lo)) * (height - M.t - M.b);
  const yt = niceTicks(lo, hi, 3);
  return (
    <div className="rh-chart-box">
      <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={ariaLabel} style={{ width: "100%", height: "auto", display: "block" }}
        onMouseLeave={() => setHov(null)}>
        {yt.map((v) => (
          <g key={v}>
            <line x1={M.l} x2={W - M.r} y1={sy(v)} y2={sy(v)} stroke={C.grid} />
            <text x={M.l - 6} y={sy(v) + 4} textAnchor="end" className="rh-axis">{fmt(v)}</text>
          </g>
        ))}
        {vals.map((v, i) => {
          const y0 = sy(0), y1 = sy(v);
          return (
            <g key={i} onMouseEnter={() => setHov(i)} onClick={() => onSelect?.(i)} style={{ cursor: onSelect ? "pointer" : "default" }}>
              <rect x={M.l + i * bw} y={M.t} width={bw} height={height - M.t - M.b} fill="transparent" />
              <rect x={M.l + i * bw + 1} y={Math.min(y0, y1)} width={Math.max(1, bw - 2)} height={Math.max(0.5, Math.abs(y1 - y0))} rx={2}
                fill={v >= 0 ? color : (negColor ?? color)} opacity={selected === undefined || selected === null || selected === i ? 1 : 0.45} />
            </g>
          );
        })}
        <line x1={M.l} x2={W - M.r} y1={sy(0)} y2={sy(0)} stroke={C.ink2} />
        {labels.map((l, i) => (i % Math.ceil(n / 12) === 0 ? (
          <text key={i} x={M.l + i * bw + bw / 2} y={height - 8} textAnchor="middle" className="rh-axis">{l}</text>
        ) : null))}
      </svg>
      {hov !== null && (
        <div className="tip rh-tip" style={{ left: `${((M.l + hov * bw) / W) * 100}%` }}>
          <b>{labels[hov]}</b><span>{values[hov] === null ? "—" : fmt(values[hov] as number)}</span>
        </div>
      )}
    </div>
  );
}
