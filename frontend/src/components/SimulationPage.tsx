import { useEffect, useMemo, useState } from "react";
import { Pause, Play, RotateCcw } from "lucide-react";
import { C, fmt } from "../theme";
import BatteryIcon, { type BatMode, MOOD_TXT, moodOf } from "./BatteryIcon";
import { useDay, useDays, useModelDay, useCompare, type Mode } from "../api/hooks";
import RollingHorizonDashboard from "./rolling/RollingHorizonDashboard";

// ---------------------------------------------------------------------------
// Types for simulation data
// ---------------------------------------------------------------------------

type Part = "solar" | "grid" | "battery" | "building" | null;
type Season = "hivern" | "primavera" | "estiu" | "tardor";
type DecAction = "carga" | "descarga" | "espera";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function sunWindow(solar: number[]) {
  const max = Math.max(...solar, 1);
  const on = solar.map((v) => v > max * 0.03);
  return { rise: Math.max(5, on.indexOf(true)), set: Math.min(22, 24 - [...on].reverse().indexOf(true)) };
}

function sourcesAt(demand: number, solar: number, discharge: number, charge: number) {
  const solarDirect = Math.min(solar, demand);
  const bat = Math.min(discharge, demand - solarDirect);
  const grid = Math.max(0, demand - solarDirect - bat + charge);
  const total = Math.max(1, demand + charge);
  return { solar: solarDirect / total, bat: bat / total, grid: grid / total };
}

function seasonOf(date: string): Season {
  const m = Number(date.slice(5, 7));
  return m === 12 || m <= 2 ? "hivern" : m <= 5 ? "primavera" : m <= 8 ? "estiu" : "tardor";
}

const LAND: Record<Season, { sky: string; lawn: string; tree: string; tree2: string; accent?: string }> = {
  primavera: { sky: "#E6F3FB", lawn: "#C9E6A6", tree: "#7DBB4E", tree2: "#9BCF6A", accent: "#F2A7C3" },
  estiu: { sky: "#DDEFFB", lawn: "#C8D98F", tree: "#4E8F37", tree2: "#5FA043" },
  tardor: { sky: "#EEF0EC", lawn: "#D7D7A8", tree: "#D58A35", tree2: "#C2662E", accent: "#E3A44A" },
  hivern: { sky: "#E6ECF1", lawn: "#D5D9C9", tree: "#8A6E55", tree2: "#8A6E55" },
};

// ---------------------------------------------------------------------------
// Mode selector
// ---------------------------------------------------------------------------

const MODES: { key: Mode; label: string; desc: string }[] = [
  { key: "estandar", label: "Estàndard", desc: "Bateria 2 MWh, ±500 kW, preus i CO₂ completament coneguts" },
  { key: "dificil", label: "Difícil", desc: "Bateria 6 MWh, ±1.500 kW, només 3 h de previsió de preu/CO₂ + meteo" },
];

// ---------------------------------------------------------------------------
// Component: SimulationPage
// ---------------------------------------------------------------------------

function SimulatorGame() {
  // --- State ---
  const [mode, setMode] = useState<Mode>("dificil");
  const [selectedDate, setSelectedDate] = useState("");
  const [hour, setHour] = useState(12);
  const [playing, setPlaying] = useState(false);
  const [focus, setFocus] = useState<Part>(null);
  const [userDecisions, setUserDecisions] = useState<Record<number, DecAction>>({});

  // --- API hooks ---
  const { days, loading: daysLoading } = useDays(mode);
  const { day, loading: dayLoading, error: dayError } = useDay(selectedDate, mode);
  const { result: modelResult, run: runModel } = useModelDay();
  const { result: compareResult, run: runCompare, reset: resetCompare } = useCompare();

  // --- Derived values ---
  const currentHour = hour;
  const userAction = userDecisions[currentHour] ?? null;
  const modelAction = modelResult?.actions[currentHour] ?? null;
  const modelPower = modelResult?.power[currentHour] ?? 0;
  const userPower = (() => {
    if (userAction === "carga") return modelResult
      ? Math.min(modelResult.power.reduce((m, v) => Math.max(m, v), 0), mode === "dificil" ? 1500 : 500)
      : 500;
    if (userAction === "descarga") return modelResult
      ? Math.min(-modelResult.power.reduce((m, v) => Math.min(m, v), 0), mode === "dificil" ? -1500 : -500)
      : -500;
    return 0;
  })();

  const gameDone = Object.keys(userDecisions).length >= 24;

  // --- Effects ---
  useEffect(() => {
    if (playing) {
      const id = setTimeout(() => setHour((h) => (h + 1) % 24), 1000);
      return () => clearTimeout(id);
    }
  }, [playing, hour]);

  useEffect(() => {
    if (selectedDate) runModel(selectedDate, mode);
  }, [selectedDate, mode, runModel]);

  useEffect(() => {
    if (gameDone && !compareResult) {
      const actions = Array.from({ length: 24 }, (_, i) => userDecisions[i] || "espera");
      runCompare(selectedDate, mode, actions);
    }
  }, [gameDone, selectedDate, mode, userDecisions, runCompare, compareResult]);

  // --- Handlers ---
  const handleDaySelect = (date: string) => {
    resetCompare();
    setSelectedDate(date);
    setHour(0);
    setUserDecisions({});
    setPlaying(false);
  };

  const handleAction = (action: DecAction) => {
    setUserDecisions((prev) => ({ ...prev, [currentHour]: action }));
    setPlaying(false);
    setHour((h) => Math.min(23, h + 1));
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!day || gameDone) return;
      const k = e.key.toLowerCase();
      if (k === "c") handleAction("carga");
      else if (k === "d") handleAction("descarga");
      else if (k === "e") handleAction("espera");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const handleReset = () => {
    resetCompare();
    setUserDecisions({});
    setHour(0);
    setPlaying(false);
  };

  // --- Computed ---
  const { rise, set } = day ? sunWindow(day.solar) : { rise: 6, set: 18 };
  const season = day ? seasonOf(day.date) : "primavera";
  const L = LAND[season];
  const isDay = currentHour >= rise && currentHour < set;

  const dem = day ? day.demand[currentHour] : 0;
  const solar = day ? Math.min(day.solar[currentHour], dem) : 0;
  const grid = day ? Math.max(0, dem - solar) : 0;
  const socPct = day && modelResult ? (modelResult.soc[currentHour] / (mode === "dificil" ? 6000 : 2000)) * 100 : 50;
  const batMode = (mode === "dificil" ? "dificil" : "estandar") as BatMode;

  const minD = day ? Math.min(...day.demand) : 0;
  const maxD = day ? Math.max(...day.demand) : 1;
  const frac = day ? (dem - minD) / Math.max(1, maxD - minD) : 0;
  const on = frac > 0.25;
  const solarFrac = day ? day.solar[currentHour] / Math.max(1, Math.max(...day.solar)) : 0;
  const cMin = day ? Math.min(...day.co2) : 0;
  const cMax = day ? Math.max(...day.co2) : 1;
  const dirt = day ? (day.co2[currentHour] - cMin) / Math.max(1e-6, cMax - cMin) : 0;

  // Sol position
  const x0 = 60, x1 = 940, yH = 300, yTop = 46;
  const t = isDay
    ? (currentHour + 0.5 - rise) / Math.max(1, set - rise)
    : ((((currentHour + 0.5 - set) % 24) + 24) % 24) / (24 - (set - rise));
  const tv = 0.15 + 0.7 * t;
  const px = x0 + (x1 - x0) * tv;
  const py = yH - 4 * (yH - yTop) * tv * (1 - tv);

  const cols = 16, rows = 2;
  const lit = Math.round((0.15 + 0.85 * frac) * cols * rows);
  const order = useMemo(() => [...Array(cols * rows).keys()].sort((a, b) => ((a * 7919) % 31) - ((b * 7919) % 31)), []);
  const litSet = new Set(order.slice(0, lit));

  const hov = (p: Part) => ({
    onMouseEnter: () => setFocus(p),
    onMouseLeave: () => setFocus(null),
    onFocus: () => setFocus(p),
    onBlur: () => setFocus(null),
    tabIndex: 0,
    style: { cursor: "pointer" },
  });

  const narrate = () => {
    if (!day) return "";
    const sun = day.solar[currentHour];
    if (sun > 5) {
      return `A les ${day.hours[currentHour]} les plaques produeixen ${fmt.int(sun)} kW, el ${fmt.int((100 * sun) / dem)} % del que demanen els edificis (${fmt.int(dem)} kW).`;
    }
    return `A les ${day.hours[currentHour]} no hi ha sol i els edificis demanen ${fmt.int(dem)} kW, tots de la xarxa.`;
  };

  const infoText = focus
    ? (() => {
        if (focus === "solar") return day
          ? `Plaques solars de la coberta: ${fmt.int(day.solar[currentHour])} kW ara.`
          : "";
        if (focus === "grid") return day
          ? `Xarxa elèctrica: el campus en compra ${fmt.int(grid)} kW. Cada kWh porta ${fmt.gCo2(day.co2[currentHour])} de CO₂ i costa ${fmt.cKwh(day.price[currentHour])}.`
          : "";
        if (focus === "battery") return `Bateria al ${Math.round(socPct)} %. ${MOOD_TXT[moodOf(socPct, batMode)]}`;
        if (focus === "building") return day
          ? `Edificis: demanen ${fmt.int(dem)} kW. ${on ? "Hi ha activitat." : "Campus gairebé apagat."}`
          : "";
        return "";
      })()
    : narrate();

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="sim-page">
      {/* Mode selector */}
      <div className="sim-header">
        <h2>🔋 Simulador interactiu</h2>
        <p className="fine">Gestiona la bateria del campus hora a hora i compara les teves decisions amb l'agent del datathon.</p>
        <div className="mode-selector">
          {MODES.map((m) => (
            <button
              key={m.key}
              className={`mode-btn ${mode === m.key ? "on" : ""}`}
              onClick={() => { setMode(m.key); setSelectedDate(""); setUserDecisions({}); setPlaying(false); resetCompare(); }}
            >
              <b>{m.label}</b>
              <small>{m.desc}</small>
            </button>
          ))}
        </div>
      </div>

      {/* Day selector */}
      <div className="sim-day-selector">
        {daysLoading ? (
          <p className="muted">Carregant dies...</p>
        ) : dayError ? (
          <p className="muted" style={{ color: "var(--bad)" }}>{dayError}</p>
        ) : (
          <>
            <p className="label">Tria un dia ({days.length} amb dades)</p>
            <div className="day-grid">
              {days.map((d) => (
                <button
                  key={d.date}
                  className={`day-btn ${selectedDate === d.date ? "on" : ""}`}
                  onClick={() => handleDaySelect(d.date)}
                >
                  <span className="day-label">{d.label}</span>
                  <span className="day-idx">{d.weekday >= 5 ? "🌙 " : "💼 "} Solar {d.solarIdx.toFixed(2)}</span>
                </button>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Main simulation view */}
      {day && !dayLoading && (
        <>
          {/* SVG Campus Visualization */}
          <div className="sim-visual">
            <svg viewBox="0 0 1000 560" className="circuit-svg" role="img">
              {/* Sky */}
              <rect x="0" y="0" width="1000" height="345" rx="16" fill={isDay ? L.sky : "#22324A"} style={{ transition: "fill .6s" }} />
              {!isDay && [[80, 50], [180, 110], [260, 40], [340, 90], [450, 30], [560, 70], [640, 40], [760, 110], [880, 60], [930, 140]].map(([sx, sy], i) => (
                <circle key={i} cx={sx} cy={sy} r={1.8} fill="#fff" opacity={0.75} />
              ))}
              <path d={`M${x0} ${yH} Q500 ${2 * yTop - yH} ${x1} ${yH}`} fill="none" stroke={isDay ? "#C3DCEB" : "#4A5D7A"} strokeWidth={2} strokeDasharray="4 8" />

              {/* Sun or Moon */}
              {isDay ? (
                <g transform={`translate(${px} ${py})`} style={{ transition: "transform .6s ease" }}>
                  <circle r={20} fill={C.solar} />
                  {[...Array(8)].map((_, i) => (
                    <line key={i} y1={-27} y2={-34} stroke={C.solar} strokeWidth={3} strokeLinecap="round" transform={`rotate(${i * 45})`} />
                  ))}
                </g>
              ) : (
                <g transform={`translate(${px} ${py})`} style={{ transition: "transform .6s ease" }}>
                  <circle r={20} fill="#F4EED3" />
                  <circle r={20} cx={9} cy={-7} fill="#22324A" />
                </g>
              )}

              {/* CO2 cloud */}
              <g {...hov("grid")} opacity={0.35 + 0.6 * dirt}>
                <g fill={isDay ? "#8F969B" : "#6E7B8C"}>
                  <circle cx="835" cy="96" r="26" /><circle cx="868" cy="82" r="32" /><circle cx="905" cy="98" r="24" />
                  <rect x="830" y="96" width="80" height="26" rx="13" />
                </g>
                <text x="868" y="104" textAnchor="middle" className="svg-cloud">CO₂ {Math.round(day.co2[currentHour] * 1000)} g</text>
              </g>

              {/* Buildings */}
              {[0, 1, 2, 3, 4].map((i) => {
                const x = 470 + i * 100, top = 170 - (i % 2) * 14;
                return (
                  <g key={i}>
                    <rect x={x} y={top} width="88" height={345 - top} fill="#B8674E" />
                    <rect x={x} y={top - 6} width="88" height="8" fill={season === "hivern" ? "#C7CCD0" : "#9AA0A3"} />
                    {[0, 1, 2, 3, 4, 5].map((r) => (
                      <rect key={r} x={x + 8} y={top + 16 + r * 24} width="72" height="7"
                        fill={isDay ? "#E9D9CF" : on ? "#F3D58A" : "#6B4A3E"} opacity={0.85} />
                    ))}
                  </g>
                );
              })}

              {/* Main building */}
              <g {...hov("building")}>
                <rect x="120" y="256" width="470" height="72" fill="#2E4B57" />
                {[...Array(cols * rows).keys()].map((k) => (
                  <rect key={k} x={130 + (k % cols) * 28.6} y={264 + Math.floor(k / cols) * 30} width="22" height="22"
                    fill={litSet.has(k) ? "#FFD36B" : "#40616E"} style={{ transition: "fill .4s" }} />
                ))}
                <rect x="88" y="238" width="534" height="20" fill="#FAFAF7" stroke="#DAD7CD" />
              </g>

              {/* Solar panels */}
              <g {...hov("solar")}>
                <polygon points="150,198 560,198 622,238 88,238" fill={season === "hivern" ? "#F6F6F3" : "#F1F0EA"} stroke="#DAD7CD" />
                {[0, 1, 2].map((r) => [...Array(11).keys()].map((c) => {
                  const y = 204 + r * 11, sk = (y - 198) / 40;
                  const xl = 150 - 62 * sk + 6, xr = 560 + 62 * sk - 6, w = (xr - xl) / 11;
                  return <rect key={`${r}-${c}`} x={xl + c * w + 1.5} y={y} width={w - 3} height={8}
                    fill="#2F5E8C" opacity={0.45 + 0.55 * solarFrac} />;
                }))}
                {solarFrac > 0.05 && <rect x="150" y="198" width="410" height="4" fill={C.solar} opacity={solarFrac} />}
              </g>

              {/* Grass and trees */}
              <rect x="0" y="328" width="1000" height="17" fill={isDay ? L.lawn : "#7C8A6E"} />
              {[34, 72, 640, 960].map((tx, i) => {
                const Ld = LAND[season];
                if (season === "hivern") {
                  return <g key={tx} stroke={Ld.tree} strokeWidth={3} strokeLinecap="round" fill="none">
                    <path d={`M${tx} 330 V292 M${tx} 304 l-12 -14 M${tx} 300 l11 -15`} />
                  </g>;
                }
                return <g key={tx}>
                  <rect x={tx - 3} y={300} width={6} height={30} fill="#7A5C3E" />
                  <circle cx={tx} cy={294} r={19} fill={i % 2 ? Ld.tree2 : Ld.tree} />
                </g>;
              })}

              {/* Power tower */}
              <g {...hov("grid")} stroke="#5D6266" strokeWidth="3" fill="none">
                <path d="M880 345 L900 150 L920 345 M887 280 H913 M892 220 H908 M870 180 H930 M876 210 H924" />
                <path d="M930 180 Q965 200 1000 185 M870 180 Q840 170 820 178" strokeWidth="1.5" />
              </g>

              {/* Battery */}
              <g {...hov("battery")}>
                <BatteryIcon id="simBat" soc={socPct} mode={batMode} x={696} y={222} w={88} h={120} />
              </g>

              {/* Underground and cables */}
              <rect x="0" y="345" width="1000" height="215" fill="#F1ECE0" />
              <line x1="0" y1="345" x2="1000" y2="345" stroke="#BDB4A0" strokeWidth="2" />

              {/* Solar cable */}
              <Cable d="M600 252 V430 H500 V448" kw={solar} color={C.solar} />
              {/* Grid cable */}
              <Cable d="M900 345 V471 H530" kw={grid} color={C.grid_} />
              {/* Battery cable */}
              <Cable d="M740 342 V515 H470 V494" kw={userPower > 1 ? userPower : userPower < -1 ? Math.abs(userPower) : 0}
                color={userPower > 1 ? C.charge : C.battery} reverse={userPower > 1} />
              {/* Building cable */}
              <Cable d="M440 448 V328" kw={dem} color="#E8B23A" />

              {/* Label */}
              <rect x="410" y="448" width="120" height="46" rx="8" fill="#fff" stroke={C.ink2} strokeWidth="2" />
              <text x="470" y="469" textAnchor="middle" className="svg-label">Quadre</text>
              <text x="470" y="485" textAnchor="middle" className="svg-small">elèctric</text>

              {/* Power labels */}
              <g className="svg-kw">
                <text x="612" y="400">☀ {fmt.int(solar)} kW</text>
                <text x="800" y="462" textAnchor="middle">Xarxa {fmt.int(grid)} kW</text>
                <text x="600" y="540" textAnchor="middle">
                  {userPower > 1 ? `→ bateria ${fmt.int(userPower)} kW`
                    : userPower < -1 ? `bateria → ${fmt.int(Math.abs(userPower))} kW`
                    : "bateria en repòs"}
                </text>
                <text x="320" y="400" textAnchor="middle">Edificis {fmt.int(dem)} kW</text>
              </g>
              <text x="20" y="372" className="svg-small">Cables soterrats · {season}</text>
            </svg>
          </div>

          {/* Side panel with controls */}
          <div className="sim-side">
            <div className="sim-clock">
              <button className="play" onClick={() => setPlaying((p) => !p)} aria-label={playing ? "Atura" : "Reprodueix"}>
                {playing ? <Pause size={20} /> : <Play size={20} />}
              </button>
              <span className="clock-big" aria-live="polite">{day.hours[currentHour]}</span>
              <span className={`pill ${on ? "pill-on" : "pill-off"}`}>{on ? "Campus encès" : "Campus apagat"}</span>
            </div>

            <div className="sim-bat-info">
              <div className="sim-bat-row">
                <span className="sim-bat-pct">Bateria {Math.round(socPct)}%</span>
                <span className={`pill pill-${userAction === "carga" ? "charge" : userAction === "descarga" ? "discharge" : "idle"}`}>
                  {userAction === "carga" ? "Carregant" : userAction === "descarga" ? "Descarregant" : "En repòs"}
                  {userPower > 1 && ` · ${fmt.int(userPower)} kW`}
                  {userPower < -1 && ` · ${fmt.int(Math.abs(userPower))} kW`}
                </span>
              </div>
              <p className="fine">{MOOD_TXT[moodOf(socPct, batMode)]}</p>
            </div>

            <p className="story-text">{focus ? infoText : narrate()}</p>

            {/* Decision buttons */}
            {!gameDone && (
              <div className="sim-actions">
                <p className="label">Què fas a les {day.hours[currentHour]}?</p>
                <div className="choices">
                  <button className="choice charge" onClick={() => handleAction("carga")}>
                    ⬆ Carregar <kbd>C</kbd>
                  </button>
                  <button className="choice espera" onClick={() => handleAction("espera")}>
                    ⏸ Esperar <kbd>E</kbd>
                  </button>
                  <button className="choice discharge" onClick={() => handleAction("descarga")}>
                    ⬇ Descarregar <kbd>D</kbd>
                  </button>
                </div>
                {modelAction && (
                  <p className="fine" style={{ marginTop: 8 }}>
                    💡 El model a les {day.hours[currentHour]}: <b>{modelAction}</b> ({fmt.int(Math.abs(modelPower))} kW)
                  </p>
                )}
              </div>
            )}

            <p className="fine">Passa per sobre de les plaques, la xarxa, la bateria o els edificis per saber-ne més.</p>
          </div>
        </>
      )}

      {/* Hour strip */}
      {day && (
        <div className="sim-bottom">
          <p className="label">D'on ve l'electricitat, hora a hora</p>
          <div className="source-strip" role="group">
            {day.hours.map((hh, h) => {
              const s = sourcesAt(day.demand[h], day.solar[h],
                compareResult?.hourly[h]?.model === "descarga" ? 200 : 0,
                compareResult?.hourly[h]?.model === "carga" ? 200 : 0);
              return (
                <button key={hh} className={h === currentHour ? "on" : ""}
                  onClick={() => { setPlaying(false); setHour(h); }}
                  title={`${hh}: sol ${Math.round(s.solar * 100)}% · xarxa ${Math.round(s.grid * 100)}%`}>
                  <span style={{ height: `${s.grid * 100}%`, background: C.grid_ }} />
                  <span style={{ height: `${s.solar * 100}%`, background: C.solar }} />
                </button>
              );
            })}
          </div>
          <div className="sim-slider">
            <input type="range" min={0} max={23} value={currentHour}
              aria-label="Hora del dia"
              onChange={(e) => { setPlaying(false); setHour(+e.target.value); }} />
            <ul className="legend">
              <li><i style={{ background: C.solar }} />Plaques solars</li>
              <li><i style={{ background: C.grid_ }} />Xarxa elèctrica</li>
            </ul>
          </div>
        </div>
      )}

      {/* Results */}
      {compareResult && gameDone && (
        <div className="sim-results">
          <div className="sim-results-header">
            <h3>Resultat final</h3>
            <button className="btn-line" onClick={handleReset}><RotateCcw size={16} /> Torna a començar</button>
          </div>

          <div className="score-bars">
            <div className="score-bar">
              <span>Tu</span>
              <div className="bar-track">
                <div className="bar-fill bar-user"
                  style={{ width: `${Math.min(100, Math.max(0, compareResult.userScore) / Math.max(Math.abs(compareResult.userScore), compareResult.modelScore) * 100, 100)}%` }} />
              </div>
              <b>{fmt.dec(compareResult.userScore, 1)} pts</b>
            </div>
            <div className="score-bar">
              <span>Model</span>
              <div className="bar-track">
                <div className="bar-fill bar-model"
                  style={{ width: `${Math.min(100, compareResult.modelScore / Math.max(Math.abs(compareResult.userScore), compareResult.modelScore) * 100, 100)}%` }} />
              </div>
              <b>{fmt.dec(compareResult.modelScore, 1)} pts</b>
            </div>
          </div>

          <div className="compare-stats">
            <div className="stat-box user-box">
              <span className="stat-label">La teva CO₂</span>
              <span className="stat-value">{fmt.dec(compareResult.user.dCO2, 1)}%</span>
            </div>
            <div className="stat-box model-box">
              <span className="stat-label">Model CO₂</span>
              <span className="stat-value">{fmt.dec(compareResult.model.dCO2, 1)}%</span>
            </div>
            <div className="stat-box user-box">
              <span className="stat-label">La teva estalvi</span>
              <span className="stat-value">{fmt.dec(compareResult.user.dCost, 1)}%</span>
            </div>
            <div className="stat-box model-box">
              <span className="stat-label">Model estalvi</span>
              <span className="stat-value">{fmt.dec(compareResult.model.dCost, 1)}%</span>
            </div>
          </div>

          {compareResult.diagnosis.length > 0 && (
            <div className="diagnosis">
              <h5>🔍 Diagnosi</h5>
              <ul>
                {compareResult.diagnosis.map((d, i) => <li key={i}>{d}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Cable component (inline to avoid import issues)
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Pàgina 6: Rolling horizon (dashboard) + joc contra l'agent
// ---------------------------------------------------------------------------

export default function SimulationPage({ initialDate }: { initialDate?: string }) {
  const [tab, setTab] = useState<"rh" | "game">("rh");
  return (
    <div className="sim-wrap">
      <div className="rh-tabs" role="tablist">
        <button role="tab" aria-selected={tab === "rh"} className={tab === "rh" ? "on" : ""} onClick={() => setTab("rh")}>
          Rolling horizon · escenaris
        </button>
        <button role="tab" aria-selected={tab === "game"} className={tab === "game" ? "on" : ""} onClick={() => setTab("game")}>
          Juga contra l'agent
        </button>
      </div>
      {tab === "rh" ? <RollingHorizonDashboard initialDate={initialDate} /> : <SimulatorGame />}
    </div>
  );
}
