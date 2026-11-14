import { Pause, Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { fmt } from "../../theme";
import type { DayData } from "../../types";
import GiantBattery, { modeAt } from "./GiantBattery";

/** Narrativa d'una hora concreta, escrita a partir de les dades (sense frases genèriques). */
function narrate(day: DayData, h: number) {
  const hh = day.hours[h];
  const sun = day.solar[h];
  const dem = day.demand[h];
  const co2 = fmt.gCo2(day.co2[h]);
  const price = fmt.cKwh(day.price[h]);
  const m = modeAt(day, h);
  const sunTxt = sun > 5
    ? `les plaques produeixen ${fmt.int(sun)} kW, que cobreixen el ${fmt.int((100 * sun) / dem)} % del que demanen els edificis (${fmt.int(dem)} kW)`
    : `no hi ha sol i els edificis demanen ${fmt.int(dem)} kW, tots de la xarxa`;
  const batTxt =
    m === "charge" ? `La xarxa va a ${co2} de CO₂ per kWh i ${price}/kWh, una de les hores bones del dia: la bateria guarda ${fmt.int(day.charge[h])} kW per fer-los servir més tard.`
    : m === "discharge" ? `La xarxa està a ${co2}/kWh i ${price}/kWh, de les hores dolentes del dia: la bateria retorna ${fmt.int(day.discharge[h])} kW i el campus en compra menys.`
    : `La xarxa està a ${co2}/kWh i ${price}/kWh. Moure energia ara no compensaria les pèrdues de la bateria, així que espera.`;
  return { hh, text: `A les ${hh} ${sunTxt}. ${batTxt}` };
}

/** Moments clau detectats automàticament al llarg del dia. */
function keyMoments(day: DayData) {
  const out: { h: number; label: string }[] = [];
  const night = Math.min(...day.demand.slice(0, 6));
  const wake = day.demand.findIndex((v, h) => h >= 5 && v > night * 1.12);
  if (wake >= 0) out.push({ h: wake, label: "S'encenen els edificis" });
  const sunPeak = day.solar.indexOf(Math.max(...day.solar));
  out.push({ h: sunPeak, label: "Pic de les plaques" });
  const clean = day.co2.indexOf(Math.min(...day.co2));
  out.push({ h: clean, label: "Xarxa més neta" });
  const firstC = day.charge.findIndex((v, h) => h >= 6 && v > 5);
  if (firstC >= 0) out.push({ h: firstC, label: "La pila comença a carregar" });
  const dirty = day.co2.indexOf(Math.max(...day.co2.slice(12))) ;
  out.push({ h: dirty, label: "Xarxa més bruta" });
  const dis = day.discharge.reduce((best, v, h) => (h >= 12 && v > day.discharge[best] ? h : best), 12);
  if (day.discharge[dis] > 5) out.push({ h: dis, label: "La pila abasteix el campus" });
  return [...new Map(out.map((o) => [o.h + o.label, o])).values()].sort((a, b) => a.h - b.h);
}

export default function ControlRoom({ day, capacityKwh, hour, setHour }:
  { day: DayData; capacityKwh: number; hour: number; setHour: (h: number) => void }) {
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => setHour((hour + 1) % 24), 900);
    return () => clearInterval(id);
  }, [playing, hour, setHour]);

  const n = narrate(day, hour);
  const moments = useMemo(() => keyMoments(day), [day]);

  return (
    <div className="control">
      <div className="control-pila">
        <p className="label">La Pila Gigant</p>
        <GiantBattery day={day} hour={hour} capacityKwh={capacityKwh} />
      </div>

      <div className="control-story">
        <div className="clock-big" aria-live="polite">{n.hh}</div>
        <p className="story-text">{n.text}</p>

        <div className="clock">
          <button className="btn-square" onClick={() => setPlaying((p) => !p)} aria-label={playing ? "Atura" : "Reprodueix el dia"}>
            {playing ? <Pause size={16} /> : <Play size={16} />}
          </button>
          <input type="range" min={0} max={23} value={hour} aria-label="Hora del dia"
            onChange={(e) => { setPlaying(false); setHour(+e.target.value); }} />
        </div>

        <ol className="moments">
          {moments.map((m) => (
            <li key={m.h + m.label}>
              <button className={m.h === hour ? "on" : ""} onClick={() => { setPlaying(false); setHour(m.h); }}>
                <b>{day.hours[m.h]}</b>{m.label}
              </button>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
