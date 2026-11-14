import { C, fmt } from "../../theme";
import type { DayData } from "../../types";

export type Mode = "charge" | "discharge" | "idle";

export function modeAt(day: DayData, h: number): Mode {
  if (day.charge[h] > 5) return "charge";
  if (day.discharge[h] > 5) return "discharge";
  return "idle";
}

const LABEL: Record<Mode, string> = {
  charge: "Carregant",
  discharge: "Abastint els edificis",
  idle: "En repòs",
};
const COLOR: Record<Mode, string> = { charge: C.charge, discharge: C.battery, idle: C.muted };

/** La "Pila Gigant": nivell de càrrega i sentit del flux d'energia a l'hora triada. */
export default function GiantBattery({ day, hour, capacityKwh }: { day: DayData; hour: number; capacityKwh: number }) {
  const soc = day.soc[hour];
  const mode = modeAt(day, hour);
  const kw = mode === "charge" ? day.charge[hour] : day.discharge[hour];
  const fillH = (168 * soc) / 100;
  const segs = 8;

  return (
    <figure className="pila">
      <svg viewBox="0 0 160 230" className="pila-svg" role="img"
        aria-label={`Bateria al ${Math.round(soc)} %, ${LABEL[mode].toLowerCase()}`}>
        <rect x="55" y="6" width="50" height="14" fill={C.ink} />
        <rect x="20" y="20" width="120" height="200" fill="#fff" stroke={C.ink} strokeWidth="6" />
        <clipPath id="pilaClip"><rect x="32" y="32" width="96" height="176" /></clipPath>
        <g clipPath="url(#pilaClip)">
          <rect x="32" y={208 - fillH} width="96" height={fillH}
            fill={mode === "charge" ? C.charge : C.battery}
            style={{ transition: "y .6s ease, height .6s ease, fill .4s" }} />
          {[...Array(segs - 1)].map((_, i) => (
            <line key={i} x1="32" x2="128" y1={32 + ((i + 1) * 176) / segs} y2={32 + ((i + 1) * 176) / segs}
              stroke="#fff" strokeWidth="3" />
          ))}
          {mode !== "idle" && (
            <g className={mode === "charge" ? "flow-up" : "flow-down"} fill="#fff">
              {[0, 1, 2].map((i) => (
                <path key={i} d="M80 0 l-12 14 h24 z"
                  transform={`translate(0 ${60 + i * 50}) ${mode === "discharge" ? "rotate(180 80 7)" : ""}`} />
              ))}
            </g>
          )}
        </g>
      </svg>
      <figcaption>
        <div className="pila-pct">{Math.round(soc)}<span>%</span></div>
        <div className="pila-state" style={{ color: COLOR[mode] }}>
          <i style={{ background: COLOR[mode] }} />{LABEL[mode]}
        </div>
        <div className="pila-sub">
          {fmt.int((soc / 100) * capacityKwh)} / {fmt.int(capacityKwh)} kWh
          {mode !== "idle" && <> · {fmt.int(kw)} kW</>}
        </div>
      </figcaption>
    </figure>
  );
}
