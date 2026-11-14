import { useEffect, useMemo, useState } from "react";
import { Pause, Play } from "lucide-react";
import { C, fmt } from "../../theme";
import type { DayData } from "../../types";
import BatteryIcon, { type BatMode, MOOD_TXT, moodOf } from "../BatteryIcon";

type Part = "solar" | "grid" | "battery" | "building" | null;
type Season = "hivern" | "primavera" | "estiu" | "tardor";

export function modeAt(day: DayData, h: number): BatMode {
  if (day.charge[h] > 5) return "charge";
  if (day.discharge[h] > 5) return "discharge";
  return "idle";
}
const MODE_TXT: Record<BatMode, string> = { charge: "Carregant", discharge: "Abastint els edificis", idle: "En repòs" };

/** Sortida i posta del sol a partir de les hores amb producció de les plaques. */
function sunWindow(day: DayData) {
  const max = Math.max(...day.solar, 1);
  const on = day.solar.map((v) => v > max * 0.03);
  return { rise: Math.max(5, on.indexOf(true)), set: Math.min(22, 24 - [...on].reverse().indexOf(true)) };
}

function sourcesAt(day: DayData, h: number) {
  const dem = Math.max(1, day.demand[h]);
  const solar = Math.min(day.solar[h], dem);
  const bat = Math.min(day.discharge[h], dem - solar);
  return { solar: solar / dem, bat: bat / dem, grid: Math.max(0, dem - solar - bat) / dem };
}

function seasonOf(date: string): Season {
  const m = Number(date.slice(5, 7));
  return m === 12 || m <= 2 ? "hivern" : m <= 5 ? "primavera" : m <= 8 ? "estiu" : "tardor";
}

/** Paleta del paisatge per estació (de dia i de nit). */
const LAND: Record<Season, { sky: string; lawn: string; tree: string; tree2: string; accent?: string }> = {
  primavera: { sky: "#E6F3FB", lawn: "#C9E6A6", tree: "#7DBB4E", tree2: "#9BCF6A", accent: "#F2A7C3" },
  estiu: { sky: "#DDEFFB", lawn: "#C8D98F", tree: "#4E8F37", tree2: "#5FA043" },
  tardor: { sky: "#EEF0EC", lawn: "#D7D7A8", tree: "#D58A35", tree2: "#C2662E", accent: "#E3A44A" },
  hivern: { sky: "#E6ECF1", lawn: "#D5D9C9", tree: "#8A6E55", tree2: "#8A6E55" },
};

function narrate(day: DayData, h: number) {
  const sun = day.solar[h], dem = day.demand[h];
  const m = modeAt(day, h);
  const sunTxt = sun > 5
    ? `les plaques produeixen ${fmt.int(sun)} kW, el ${fmt.int((100 * sun) / dem)} % del que demanen els edificis (${fmt.int(dem)} kW)`
    : `no hi ha sol i els edificis demanen ${fmt.int(dem)} kW, tots de la xarxa`;
  const co2 = fmt.gCo2(day.co2[h]), price = fmt.cKwh(day.price[h]);
  const batTxt =
    m === "charge" ? `La xarxa va a ${co2} de CO₂ per kWh i ${price}/kWh, una de les hores bones del dia: la bateria guarda ${fmt.int(day.charge[h])} kW per fer-los servir més tard.`
    : m === "discharge" ? `La xarxa està a ${co2}/kWh i ${price}/kWh, de les hores dolentes del dia: la bateria retorna ${fmt.int(day.discharge[h])} kW i el campus en compra menys.`
    : `La xarxa està a ${co2}/kWh i ${price}/kWh. Moure energia ara no compensaria les pèrdues de la bateria, així que espera.`;
  return `A les ${day.hours[h]} ${sunTxt}. ${batTxt}`;
}

function Cable({ d, kw, color, reverse = false }: { d: string; kw: number; color: string; reverse?: boolean }) {
  const on = kw > 3;
  return (
    <g>
      <path d={d} fill="none" stroke="#CBC3B0" strokeWidth={12} strokeLinecap="round" strokeLinejoin="round" />
      <path d={d} fill="none" stroke="#F7F4EC" strokeWidth={6} strokeLinecap="round" strokeLinejoin="round" />
      {on && (
        <path d={d} fill="none" stroke={color} strokeWidth={3 + Math.min(7, kw / 120)} strokeLinecap="round"
          strokeLinejoin="round" strokeDasharray="10 14" className={`cable-flow ${reverse ? "rev" : ""}`}
          style={{ animationDuration: `${Math.max(0.5, 3.2 - kw / 260).toFixed(2)}s` }} />
      )}
    </g>
  );
}

/** Arbre segons l'estació: fullatge, flors, fulles caigudes o branques nues. */
function Tree({ x, season, i }: { x: number; season: Season; i: number }) {
  const L = LAND[season];
  if (season === "hivern") {
    return (
      <g stroke={L.tree} strokeWidth={3} strokeLinecap="round" fill="none">
        <path d={`M${x} 330 V292 M${x} 304 l-12 -14 M${x} 300 l11 -15 M${x} 292 l-7 -12 M${x} 292 l6 -11`} />
      </g>
    );
  }
  return (
    <g>
      <rect x={x - 3} y={300} width={6} height={30} fill="#7A5C3E" />
      <circle cx={x} cy={294} r={19} fill={i % 2 ? L.tree2 : L.tree} />
      {L.accent && [[-8, -6], [7, -10], [2, 4], [-10, 6], [10, 3]].map(([dx, dy], k) => (
        <circle key={k} cx={x + dx} cy={294 + dy} r={season === "primavera" ? 2.6 : 2.2} fill={L.accent} />
      ))}
      {season === "tardor" && [[-16, 32], [14, 34], [24, 30]].map(([dx, dy], k) => (
        <ellipse key={k} cx={x + dx} cy={294 + dy} rx={3} ry={1.6} fill={L.accent} />
      ))}
    </g>
  );
}

export default function CampusLive({ day, hour, setHour }: { day: DayData; hour: number; setHour: (h: number) => void }) {
  const [focus, setFocus] = useState<Part>(null);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!playing) return;
    const id = setTimeout(() => setHour((hour + 1) % 24), 1000);
    return () => clearTimeout(id);
  }, [playing, hour, setHour]);

  const { rise, set } = useMemo(() => sunWindow(day), [day]);
  const season = seasonOf(day.date);
  const L = LAND[season];
  const isDay = hour >= rise && hour < set;

  const dem = day.demand[hour];
  const solar = Math.min(day.solar[hour], dem);
  const dis = day.discharge[hour], chg = day.charge[hour];
  const grid = Math.max(0, dem - solar - dis + chg);
  const soc = day.soc[hour];
  const mode = modeAt(day, hour);

  const minD = Math.min(...day.demand), maxD = Math.max(...day.demand);
  const frac = (dem - minD) / Math.max(1, maxD - minD);
  const on = frac > 0.25;
  const solarFrac = day.solar[hour] / Math.max(1, Math.max(...day.solar));
  const cMin = Math.min(...day.co2), cMax = Math.max(...day.co2);
  const dirt = (day.co2[hour] - cMin) / Math.max(1e-6, cMax - cMin);

  // Sol i lluna recorren el mateix arc (paràbola) entre l'horitzó i el zenit
  const x0 = 60, x1 = 940, yH = 300, yTop = 46;
  const t = isDay ? (hour + 0.5 - rise) / (set - rise) : ((((hour + 0.5 - set) % 24) + 24) % 24) / (24 - (set - rise));
  // Es limita el recorregut (15–85 % de l'arc) perquè el sol i la lluna no quedin amagats darrere dels edificis
  const tv = 0.15 + 0.7 * t;
  const px = x0 + (x1 - x0) * tv, py = yH - 4 * (yH - yTop) * tv * (1 - tv);

  const cols = 16, rows = 2;
  const lit = Math.round((0.15 + 0.85 * frac) * cols * rows);
  const order = useMemo(() => [...Array(cols * rows).keys()].sort((a, b) => ((a * 7919) % 31) - ((b * 7919) % 31)), []);
  const litSet = new Set(order.slice(0, lit));

  const info: Record<Exclude<Part, null>, string> = {
    solar: `Plaques solars de la coberta: ${fmt.int(day.solar[hour])} kW ara. Aquest dia n'han produït ${fmt.int(day.totals.solarKwh)} kWh, el ${fmt.dec(day.totals.solarShare)} % del consum.`,
    grid: `Xarxa elèctrica: el campus en compra ${fmt.int(grid)} kW${chg > 5 ? ` (${fmt.int(chg)} kW van a la bateria)` : ""}. Cada kWh porta ${fmt.gCo2(day.co2[hour])} de CO₂ i costa ${fmt.cKwh(day.price[hour])}.`,
    battery: `Bateria de 2 MWh al ${Math.round(soc)} %. ${MOOD_TXT[moodOf(soc, mode)]}.`,
    building: `Edificis: demanen ${fmt.int(dem)} kW. ${on ? "Hi ha activitat docent i de recerca." : `Campus gairebé apagat: és el consum de fons (mínim del dia ${fmt.int(minD)} kW).`}`,
  };
  const hov = (p: Part) => ({ onMouseEnter: () => setFocus(p), onMouseLeave: () => setFocus(null),
    onFocus: () => setFocus(p), onBlur: () => setFocus(null), tabIndex: 0, style: { cursor: "pointer" } });

  return (
    <div className="card live">
      <div className="live-grid">
        <div className="live-visual">
          <svg viewBox="0 0 1000 560" className="circuit-svg" role="img"
            aria-label={`Campus a les ${day.hours[hour]} (${season}): solar ${fmt.int(solar)} kW, xarxa ${fmt.int(grid)} kW, bateria al ${Math.round(soc)} % ${MODE_TXT[mode].toLowerCase()}, edificis ${fmt.int(dem)} kW`}>
            {/* Cel, estrelles, arc, sol o lluna */}
            <rect x="0" y="0" width="1000" height="345" rx="16" fill={isDay ? L.sky : "#22324A"} style={{ transition: "fill .6s" }} />
            {!isDay && [[80, 50], [180, 110], [260, 40], [340, 90], [450, 30], [560, 70], [640, 40], [760, 110], [880, 60], [930, 140]].map(([sx, sy], i) => (
              <circle key={i} cx={sx} cy={sy} r={1.8} fill="#fff" opacity={0.75} />
            ))}
            <path d={`M${x0} ${yH} Q500 ${2 * yTop - yH} ${x1} ${yH}`} fill="none" stroke={isDay ? "#C3DCEB" : "#4A5D7A"} strokeWidth={2} strokeDasharray="4 8" />
            {isDay ? (
              <g transform={`translate(${px} ${py})`} style={{ transition: "transform .6s ease" }}>
                <circle r={20} fill={C.solar} />
                {[...Array(8)].map((_, i) => <line key={i} y1={-27} y2={-34} stroke={C.solar} strokeWidth={3} strokeLinecap="round" transform={`rotate(${i * 45})`} />)}
              </g>
            ) : (
              <g transform={`translate(${px} ${py})`} style={{ transition: "transform .6s ease" }}>
                <circle r={20} fill="#F4EED3" />
                <circle r={20} cx={9} cy={-7} fill="#22324A" />
              </g>
            )}

            {/* Núvol de CO₂ */}
            <g {...hov("grid")} opacity={0.35 + 0.6 * dirt}>
              <g fill={isDay ? "#8F969B" : "#6E7B8C"}>
                <circle cx="835" cy="96" r="26" /><circle cx="868" cy="82" r="32" /><circle cx="905" cy="98" r="24" /><rect x="830" y="96" width="80" height="26" rx="13" />
              </g>
              <text x="868" y="104" textAnchor="middle" className="svg-cloud">CO₂ {Math.round(day.co2[hour] * 1000)} g</text>
            </g>

            {/* Edificis de maó */}
            {[0, 1, 2, 3, 4].map((i) => {
              const x = 470 + i * 100, top = 170 - (i % 2) * 14;
              return (
                <g key={i}>
                  <rect x={x} y={top} width="88" height={345 - top} fill="#B8674E" />
                  <rect x={x} y={top - 6} width="88" height="8" fill={season === "hivern" ? "#C7CCD0" : "#9AA0A3"} />
                  {[0, 1, 2, 3, 4, 5].map((r) => (
                    <rect key={r} x={x + 8} y={top + 16 + r * 24} width="72" height="7" fill={isDay ? "#E9D9CF" : on ? "#F3D58A" : "#6B4A3E"} opacity={0.85} />
                  ))}
                </g>
              );
            })}

            {/* Edifici principal */}
            <g {...hov("building")}>
              <rect x="120" y="256" width="470" height="72" fill="#2E4B57" />
              {[...Array(cols * rows).keys()].map((k) => (
                <rect key={k} x={130 + (k % cols) * 28.6} y={264 + Math.floor(k / cols) * 30} width="22" height="22"
                  fill={litSet.has(k) ? "#FFD36B" : "#40616E"} style={{ transition: "fill .4s" }} />
              ))}
              <rect x="88" y="238" width="534" height="20" fill="#FAFAF7" stroke="#DAD7CD" />
            </g>
            <g {...hov("solar")}>
              <polygon points="150,198 560,198 622,238 88,238" fill={season === "hivern" ? "#F6F6F3" : "#F1F0EA"} stroke="#DAD7CD" />
              {[0, 1, 2].map((r) => [...Array(11).keys()].map((c) => {
                const y = 204 + r * 11, sk = (y - 198) / 40;
                const xl = 150 - 62 * sk + 6, xr = 560 + 62 * sk - 6, w = (xr - xl) / 11;
                return <rect key={`${r}-${c}`} x={xl + c * w + 1.5} y={y} width={w - 3} height={8} fill="#2F5E8C" opacity={0.45 + 0.55 * solarFrac} />;
              }))}
              {solarFrac > 0.05 && <rect x="150" y="198" width="410" height="4" fill={C.solar} opacity={solarFrac} />}
            </g>

            {/* Gespa i arbres segons l'estació */}
            <rect x="0" y="328" width="1000" height="17" fill={isDay ? L.lawn : "#7C8A6E"} />
            {[34, 72, 640, 960].map((tx, i) => <Tree key={tx} x={tx} season={season} i={i} />)}

            {/* Torre elèctrica */}
            <g {...hov("grid")} stroke="#5D6266" strokeWidth="3" fill="none">
              <path d="M880 345 L900 150 L920 345 M887 280 H913 M892 220 H908 M870 180 H930 M876 210 H924" />
              <path d="M930 180 Q965 200 1000 185 M870 180 Q840 170 820 178" strokeWidth="1.5" />
            </g>

            {/* La bateria (la mateixa del panell) */}
            <g {...hov("battery")}>
              <BatteryIcon id="liveBat" soc={soc} mode={mode} x={696} y={222} w={88} h={120} />
            </g>

            {/* Subsòl i cables */}
            <rect x="0" y="345" width="1000" height="215" fill="#F1ECE0" />
            <line x1="0" y1="345" x2="1000" y2="345" stroke="#BDB4A0" strokeWidth="2" />
            <Cable d="M600 252 V430 H500 V448" kw={solar} color={C.solar} />
            <Cable d="M900 345 V471 H530" kw={grid} color={C.grid_} />
            <Cable d="M740 342 V515 H470 V494" kw={chg > 5 ? chg : dis} color={chg > 5 ? C.charge : C.battery} reverse={chg > 5} />
            <Cable d="M440 448 V328" kw={dem} color="#E8B23A" />
            <rect x="410" y="448" width="120" height="46" rx="8" fill="#fff" stroke={C.ink2} strokeWidth="2" />
            <text x="470" y="469" textAnchor="middle" className="svg-label">Quadre</text>
            <text x="470" y="485" textAnchor="middle" className="svg-small">elèctric</text>
            <g className="svg-kw">
              <text x="612" y="400">☀ {fmt.int(solar)} kW</text>
              <text x="800" y="462" textAnchor="middle">Xarxa {fmt.int(grid)} kW</text>
              <text x="600" y="540" textAnchor="middle">{chg > 5 ? `→ bateria ${fmt.int(chg)} kW` : dis > 5 ? `bateria → ${fmt.int(dis)} kW` : "bateria en repòs"}</text>
              <text x="320" y="400" textAnchor="middle">Edificis {fmt.int(dem)} kW</text>
            </g>
            <text x="20" y="372" className="svg-small">Cables soterrats · {season}</text>
          </svg>
        </div>

        <div className="live-side">
          <div className="live-clock">
            <button className="play" onClick={() => setPlaying((p) => !p)} aria-label={playing ? "Atura" : "Reprodueix el dia"}>
              {playing ? <Pause size={20} /> : <Play size={20} />}
            </button>
            <span className="clock-big" aria-live="polite">{day.hours[hour]}</span>
            <span className={`pill ${on ? "pill-on" : "pill-off"}`}>{on ? "Campus encès" : "Campus apagat"}</span>
          </div>
          <div className="bat-status">
            <span className="bat-pct">Bateria {Math.round(soc)} %</span>
            <span className={`pill pill-${mode}`}>{MODE_TXT[mode]}{mode !== "idle" && ` · ${fmt.int(mode === "charge" ? chg : dis)} kW`}</span>
          </div>
          <p className="fine">{MOOD_TXT[moodOf(soc, mode)]}</p>
          <p className="story-text">{focus ? info[focus] : narrate(day, hour)}</p>
          <p className="fine">Passa per sobre de les plaques, la xarxa, la bateria o els edificis per saber-ne més.</p>
        </div>
      </div>

      <div className="live-bottom">
        <p className="label">D'on ve l'electricitat, hora a hora</p>
        <div className="source-strip" role="group" aria-label="Origen de l'electricitat per hora">
          {day.hours.map((hh, h) => {
            const s = sourcesAt(day, h);
            return (
              <button key={hh} className={h === hour ? "on" : ""} onClick={() => { setPlaying(false); setHour(h); }}
                title={`${hh} · sol ${Math.round(s.solar * 100)} % · bateria ${Math.round(s.bat * 100)} % · xarxa ${Math.round(s.grid * 100)} %`}
                aria-label={`${hh}: sol ${Math.round(s.solar * 100)} %, bateria ${Math.round(s.bat * 100)} %, xarxa ${Math.round(s.grid * 100)} %`}>
                <span style={{ height: `${s.grid * 100}%`, background: C.grid_ }} />
                <span style={{ height: `${s.bat * 100}%`, background: C.battery }} />
                <span style={{ height: `${s.solar * 100}%`, background: C.solar }} />
              </button>
            );
          })}
        </div>
        <div className="live-slider">
          <input type="range" min={0} max={23} value={hour} aria-label="Hora del dia"
            onChange={(e) => { setPlaying(false); setHour(+e.target.value); }} />
          <ul className="legend">
            <li><i style={{ background: C.solar }} />Plaques solars</li>
            <li><i style={{ background: C.battery }} />Bateria</li>
            <li><i style={{ background: C.grid_ }} />Xarxa elèctrica (amb CO₂)</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
