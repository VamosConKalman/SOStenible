import { useEffect, useMemo } from "react";
import { ArrowDownToLine, ArrowUpFromLine, Hourglass, RotateCcw, Undo2 } from "lucide-react";
import { fmt, tercile } from "../../theme";
import type { DayData } from "../../types";
import { type Action, type Battery, baseline, decisionPoints, hourWeights, optimalRun, runActions, step } from "../../lib/energy";
import ForecastChart from "./ForecastChart";
import BatteryIcon, { MOOD_TXT, moodOf } from "../BatteryIcon";

interface Props {
  day: DayData;
  bat: Battery;
  actions: Action[];
  setActions: (a: Action[]) => void;
  onAnalyse: () => void;
}

/** Frase que combina CO₂ i preu de l'hora (terç baix / mitjà / alt de cada un). */
const SENT: Record<string, Record<string, string>> = {
  good: { good: "una hora neta i barata.", warn: "una hora neta, a preu mitjà.", bad: "neta, però cara." },
  warn: { good: "barata, amb un CO₂ normal.", warn: "una hora del muntó.", bad: "cara, amb un CO₂ normal." },
  bad: { good: "barata, però bruta.", warn: "una hora bruta, a preu mitjà.", bad: "una hora bruta i cara." },
};

/** Escala del dia (mínim → màxim) amb la posició de l'hora actual. */
function DayGauge({ label, values, h, fmtV }: { label: string; values: number[]; h: number; fmtV: (v: number) => string }) {
  const mn = Math.min(...values), mx = Math.max(...values);
  const pos = (100 * (values[h] - mn)) / Math.max(1e-9, mx - mn);
  return (
    <div className="gauge">
      <span className="gauge-label">{label}</span>
      <span className="gauge-min">{fmtV(mn)}</span>
      <span className="gauge-track" role="img" aria-label={`${label}: ${fmtV(values[h])}, entre ${fmtV(mn)} i ${fmtV(mx)} aquest dia`}>
        {values.map((v, k) => <i key={k} style={{ left: `${(100 * (v - mn)) / Math.max(1e-9, mx - mn)}%` }} />)}
        <b style={{ left: `${pos}%` }}>{fmtV(values[h])}</b>
      </span>
      <span className="gauge-max">{fmtV(mx)}</span>
    </div>
  );
}

/** Frase final segons el rendiment respecte al model. */
function verdict(ratio: number) {
  if (ratio >= 0.95) return { title: "Has aconseguit predir el mateix que el model!", text: "Les teves decisions estalvien pràcticament el mateix CO₂ i diners que l'algorisme." };
  if (ratio >= 0.75) return { title: "Molt a prop del model", text: "Has encertat les hores importants; només unes quantes decisions et separen del resultat òptim." };
  if (ratio >= 0.4) return { title: "Vas pel bon camí", text: "Has estalviat, però el model ha trobat hores millors per carregar i descarregar." };
  if (ratio > 0) return { title: "No has arribat al que proposava el model", text: "Has estalviat una mica, però lluny del que aconsegueix l'algorisme. Mira l'anàlisi per veure per què." };
  return { title: "No has aconseguit el que el model proposava", text: "Amb aquestes decisions el campus ha emès més CO₂ o ha pagat més que sense bateria. Torna-ho a provar!" };
}

const ACT: Record<Action, { label: string; key: string; Icon: typeof Hourglass }> = {
  charge: { label: "Carregar", key: "C", Icon: ArrowDownToLine },
  discharge: { label: "Descarregar", key: "D", Icon: ArrowUpFromLine },
  wait: { label: "Esperar", key: "E", Icon: Hourglass },
};
const STATE_TXT = { good: "de les més baixes del dia", warn: "en la mitjana del dia", bad: "de les més altes del dia" };

/** Text d'ajuda (abans era el bloc "Com es juga"). */
export const HOW_TO = "Comences a mitjanit amb la bateria al 50 %. Cada hora decideixes si carregues (500 kW), descarregues o esperes; també pots fer servir les tecles C, D i E. Els punts mesuren quant redueixes el CO₂ (70 %) i el cost (30 %) del dia. Pista: fixa't en la previsió; l'hora més valuosa per descarregar acostuma a arribar al vespre.";

/** Reprodueix la partida fins a l'hora actual per saber l'estat de la bateria i els punts. */
function replay(day: DayData, bat: Battery, actions: Action[]) {
  let soc = bat.soc0;
  const log = actions.map((a, h) => {
    const r = decisionPoints(day, bat, h, soc, a);
    const before = soc;
    soc = r.soc;
    return { a, h, pts: r.pts, before, after: soc, c: r.c, d: r.d, limited: r.limited };
  });
  return { soc, log, total: log.reduce((s, l) => s + l.pts, 0) };
}

function explain(day: DayData, bat: Battery, e: ReturnType<typeof replay>["log"][number]) {
  const w = hourWeights(day);
  const { h, a } = e;
  const tc = tercile(day.co2, day.co2[h]);
  const later = [...Array(24).keys()].filter((k) => k > h);
  const peak = later.length ? later.reduce((x, y) => (w[y] > w[x] ? y : x)) : -1;
  const g = fmt.gCo2(day.co2[h]);
  if (a === "charge") {
    if (e.c < 1) return "La bateria ja era plena: no hi cabia res més. Una bateria plena no aprofita les hores bones.";
    if (e.limited) return `Només hi cabien ${fmt.int(e.c)} kWh. Has omplert la bateria${tc === "good" ? " en una hora neta: bona feina" : ""}.`;
    if (e.pts > 0.05) return `Has aprofitat una hora ${tc === "good" ? "molt neta" : "raonable"} (${g} CO₂/kWh) per emmagatzemar energia. ${peak >= 0 ? `Més tard, a les ${day.hours[peak]}, la xarxa serà ${fmt.gCo2(day.co2[peak])}/kWh.` : ""}`;
    return `Carregar a ${g} CO₂/kWh i ${fmt.cKwh(day.price[h])}/kWh no compensa: les hores que queden no són prou més cares ni més brutes per cobrir el 10 % de pèrdues.`;
  }
  if (a === "discharge") {
    if (e.d < 1) return "La bateria era buida: no hi havia res a treure. Cal carregar abans les hores bones.";
    if (e.pts > 0.05) return `Bona tria: ara la xarxa és ${g} CO₂/kWh (${STATE_TXT[tc]}) i el campus compra ${fmt.int(e.d)} kWh menys.`;
    return peak >= 0 && w[peak] > w[h]
      ? `Has descarregat massa aviat. A les ${day.hours[peak]} hi haurà una hora més cara (${fmt.cKwh(day.price[peak])}/kWh) i més contaminant (${fmt.gCo2(day.co2[peak])}/kWh).`
      : `Ara la xarxa està a ${g}/kWh, ${STATE_TXT[tc]}. L'energia guardada valdria més en una hora pitjor.`;
  }
  const room = e.before < bat.cap - 100, stock = e.before > 100;
  if (tc === "good" && room) return `Has deixat passar una hora neta (${g}/kWh) amb espai a la bateria. Potser era moment de carregar.`;
  if (tc === "bad" && stock) return `Era una hora bruta (${g}/kWh) i la bateria tenia energia. Potser era moment de descarregar.`;
  return "Esperar també és una decisió: ara no hi havia prou diferència per moure energia.";
}

export default function DecisionGame({ day, bat, actions, setActions, onAnalyse }: Props) {
  const h = actions.length;
  const done = h >= 24;
  const { net } = useMemo(() => baseline(day), [day]);
  const st = useMemo(() => replay(day, bat, actions), [day, bat, actions]);
  const last = st.log[st.log.length - 1];

  const decide = (a: Action) => { if (!done) setActions([...actions, a]); };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT") return;
      const k = e.key.toLowerCase();
      if (k === "c") decide("charge");
      if (k === "d") decide("discharge");
      if (k === "e") decide("wait");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const socPct = (100 * st.soc) / bat.cap;
  /** Nivell de bateria després de cada opció (sense revelar-ne la puntuació). */
  const nextSoc = (a: Action) => (100 * step(bat, st.soc, net[Math.min(h, 23)], a).soc) / bat.cap;
  const batMode = last?.a === "charge" && last.c > 1 ? "charge" : last?.a === "discharge" && last.d > 1 ? "discharge" : "idle";

  return (
    <div className="game">
      <ol className="track" aria-label="Decisions preses">
        {day.hours.map((hh, i) => {
          const l = st.log[i];
          const Icon = l ? ACT[l.a].Icon : null;
          return (
            <li key={hh} className={`${i === h ? "now" : ""} ${l ? (l.pts > 0.05 ? "pos" : l.pts < -0.05 ? "neg" : "zero") : ""}`}
              title={l ? `${hh} · ${ACT[l.a].label} · ${fmt.pts(l.pts)} punts` : hh}>
              {Icon ? <Icon size={14} aria-hidden /> : <span>{i % 3 === 0 ? hh.slice(0, 2) : ""}</span>}
            </li>
          );
        })}
      </ol>

      <div className="game-grid">
        {!done ? (
          <section className="situation" aria-live="polite">
            <div className="sit-integrated">
              <figure className="sit-bat">
                <svg viewBox="0 0 120 160" role="img" aria-label={`Bateria al ${Math.round(socPct)} %`}>
                  <BatteryIcon id="gameBat" soc={socPct} mode={batMode} x={6} y={2} w={108} h={154} />
                </svg>
                <figcaption><b>{fmt.int(socPct)} %</b><span>{MOOD_TXT[moodOf(socPct, batMode)]}</span></figcaption>
              </figure>
              <div className="sit-main">
                <div className="sit-hour">{day.hours[h]}</div>
                <p className="sit-sentence">
                  El campus consumeix <b>{fmt.int(net[h])} kW</b>. La xarxa emet <b>{fmt.gCo2(day.co2[h])} de CO₂/kWh</b> i
                  {" "}costa <b>{fmt.cKwh(day.price[h])}/kWh</b>: {SENT[tercile(day.co2, day.co2[h])][tercile(day.price, day.price[h])]}
                </p>
                <DayGauge label="CO₂ de la xarxa" values={day.co2} h={h} fmtV={(v) => `${Math.round(v * 1000)} g`} />
                <DayGauge label="Preu" values={day.price} h={h} fmtV={(v) => `${fmt.dec(v * 100, 1)} c€`} />
              </div>
            </div>

            <p className="label">Quina decisió prens?</p>
            <div className="choices">
              {(Object.keys(ACT) as Action[]).map((a) => {
                const { label, key, Icon } = ACT[a];
                return (
                  <button key={a} className={`choice ${a}`} onClick={() => decide(a)}>
                    <Icon size={22} aria-hidden /><span>{label}</span><kbd>{key}</kbd>
                    <small className="choice-soc">{fmt.int(socPct)} % → {fmt.int(nextSoc(a))} %</small>
                  </button>
                );
              })}
            </div>

          </section>
        ) : (
          <section className="situation done">
            <FinalScore day={day} bat={bat} actions={actions} onAnalyse={onAnalyse} />
          </section>
        )}

        <section className="verdict compact">
          <div className="score-total">
            <p className="label">Punts de les decisions</p>
            <div className={`score-big ${st.total >= 0 ? "pos" : "neg"}`}>{fmt.pts(st.total)}</div>
            <p className="fine">{h}/24 hores decidides · orientatiu; la puntuació oficial és a la secció 3.</p>
          </div>

          {last ? (
            <div className={`last ${last.pts > 0.05 ? "pos" : last.pts < -0.05 ? "neg" : "zero"}`}>
              <p className="label">{day.hours[last.h]} · La teva decisió</p>
              <p className="last-act">{ACT[last.a].label}</p>
              <p className="last-pts">Resultat: <b>{fmt.pts(last.pts)} punts</b></p>
              <p className="last-why"><b>Explicació. </b>{explain(day, bat, last)}</p>
            </div>
          ) : (
            <p className="muted">Aquí veuràs el resultat i l'explicació de cada decisió.</p>
          )}

          <div className="btn-row">
            <button className="btn-line" disabled={!h} onClick={() => setActions(actions.slice(0, -1))}><Undo2 size={16} /> Desfés</button>
            <button className="btn-line" disabled={!h} onClick={() => setActions([])}><RotateCcw size={16} /> Torna a començar</button>
          </div>
        </section>
      </div>

      {!done && <ForecastChart day={day} h={h} socPct={socPct} />}
    </div>
  );
}

/** Resultat final: puntuació de l'usuari contra la del model i frase segons el rendiment. */
function FinalScore({ day, bat, actions, onAnalyse }: { day: DayData; bat: Battery; actions: Action[]; onAnalyse: () => void }) {
  const user = runActions(day, bat, actions);
  const model = optimalRun(day, bat);
  const ratio = model.score > 0 ? user.score / model.score : 0;
  const modelAct = (h: number): Action => (day.charge[h] > 5 ? "charge" : day.discharge[h] > 5 ? "discharge" : "wait");
  const same = actions.filter((a, h) => a === modelAct(h)).length;
  const v = verdict(ratio);
  const pct = Math.max(0, Math.min(100, ratio * 100));
  return (
    <div className="final">
      <p className="label">Resultat final</p>
      <h3 className={`final-title ${ratio >= 0.75 ? "good" : ratio >= 0.4 ? "mid" : "low"}`}>{v.title}</h3>
      <p>{v.text}</p>
      <div className="final-bars">
        <div><span>La teva estratègia</span><b>{fmt.dec(user.score, 1)} punts</b>
          <span className="fbar"><span style={{ width: `${pct}%`, background: "var(--charge)" }} /></span></div>
        <div><span>El model</span><b>{fmt.dec(model.score, 1)} punts</b>
          <span className="fbar"><span style={{ width: "100%", background: "var(--upc)" }} /></span></div>
      </div>
      <dl className="final-facts">
        <div><dt>{fmt.int(ratio * 100)} %</dt><dd>de l'estalvi del model</dd></div>
        <div><dt>{same}/24</dt><dd>hores amb la mateixa decisió</dd></div>
        <div><dt>{fmt.int(user.co2SavedKg)} kg</dt><dd>de CO₂ estalviats</dd></div>
      </dl>
      <button className="btn-solid" onClick={onAnalyse}>Analitza la teva estratègia</button>
    </div>
  );
}
