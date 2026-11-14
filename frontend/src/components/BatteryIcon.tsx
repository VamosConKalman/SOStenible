import { C } from "../theme";

export type BatMode = "charge" | "discharge" | "idle";

export type Mood = "happy" | "ok" | "sad" | "tired";

/** Cara: cansada mentre es descarrega; si no, segons la càrrega:
 *  contenta (≥ 60 %), tranquil·la (30–60 %) o trista (< 30 %). */
export function moodOf(soc: number, mode: BatMode = "idle"): Mood {
  if (mode === "discharge") return "tired";
  return soc >= 60 ? "happy" : soc >= 30 ? "ok" : "sad";
}

export const MOOD_TXT: Record<Mood, string> = {
  happy: "Contenta: va ben carregada",
  ok: "Tranquil·la: a mitja càrrega",
  sad: "Trista: gairebé buida",
  tired: "Cansada: està donant energia als edificis",
};

interface Props {
  soc: number;          // 0–100
  mode: BatMode;
  x?: number; y?: number; w?: number; h?: number;
  id: string;           // per al clipPath (ha de ser únic a la pàgina)
}

/** Bateria vectorial amb nivell, sentit del flux i cara. Es dibuixa dins d'un <svg>. */
export default function BatteryIcon({ soc, mode, x = 0, y = 0, w = 120, h = 190, id }: Props) {
  const r = 14;
  const innerX = x + 9, innerY = y + 16, innerW = w - 18, innerH = h - 25;
  const fillH = (innerH * Math.max(0, Math.min(100, soc))) / 100;
  const fill = mode === "charge" ? C.charge : C.battery;
  const mood = moodOf(soc, mode);
  const cx = x + w / 2, fy = y + h * 0.42;

  return (
    <g>
      <rect x={cx - w * 0.2} y={y} width={w * 0.4} height={10} rx={4} fill={C.ink2} />
      <rect x={x} y={y + 7} width={w} height={h - 7} rx={r} fill="#fff" stroke={C.ink2} strokeWidth={4} />
      <clipPath id={id}><rect x={innerX} y={innerY} width={innerW} height={innerH} rx={r - 6} /></clipPath>
      <g clipPath={`url(#${id})`}>
        <rect x={innerX} y={innerY + innerH - fillH} width={innerW} height={fillH + 1} fill={fill} opacity={0.88}
          style={{ transition: "y .5s ease, height .5s ease, fill .3s" }} />
        {mode !== "idle" && (
          <g className={mode === "charge" ? "flow-up" : "flow-down"} fill="#fff" opacity={0.75}>
            {[0, 1].map((i) => (
              <path key={i} d={`M${cx} 0 l-9 11 h18 z`}
                transform={`translate(0 ${innerY + innerH * 0.55 + i * innerH * 0.25}) ${mode === "discharge" ? `rotate(180 ${cx} 5.5)` : ""}`} />
            ))}
          </g>
        )}
      </g>
      {/* Cara */}
      <g stroke={C.ink} strokeWidth={4} strokeLinecap="round" fill="none" aria-hidden>
        {mood === "tired" ? (
          <>
            {/* ulls mig closos i gota de suor */}
            <path d={`M${cx - w * 0.24} ${fy} q${w * 0.07} ${4} ${w * 0.14} 0`} />
            <path d={`M${cx + w * 0.1} ${fy} q${w * 0.07} ${4} ${w * 0.14} 0`} />
            <path d={`M${cx + w * 0.3} ${fy - 14} q-5 9 0 12 q5 -3 0 -12z`} fill="#7FC4EA" stroke="#4A9BC9" strokeWidth={1.5} />
          </>
        ) : (
          <>
            <circle cx={cx - w * 0.17} cy={fy} r={2.5} fill={C.ink} />
            <circle cx={cx + w * 0.17} cy={fy} r={2.5} fill={C.ink} />
          </>
        )}
        {mood === "tired" && <path d={`M${cx - w * 0.14} ${fy + 20} q${w * 0.07} ${-4} ${w * 0.14} 0 t${w * 0.14} 0`} />}
        {mood === "happy" && <path d={`M${cx - w * 0.2} ${fy + 14} q${w * 0.2} ${18} ${w * 0.4} 0`} />}
        {mood === "ok" && <path d={`M${cx - w * 0.17} ${fy + 18} q${w * 0.17} ${6} ${w * 0.34} 0`} />}
        {mood === "sad" && <path d={`M${cx - w * 0.2} ${fy + 24} q${w * 0.2} ${-16} ${w * 0.4} 0`} />}
      </g>
    </g>
  );
}
