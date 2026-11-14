import { useEffect, useMemo } from "react";
import { ArrowDownToLine, ArrowUpFromLine, Hourglass, RotateCcw, Undo2 } from "lucide-react";
import { fmt, tercile } from "../../theme";
import type { DayData } from "../../types";
import { type Action, type Battery, baseline, decisionPoints, hourWeights } from "../../lib/energy";

interface Props {
  day: DayData;
  bat: Battery;
  actions: Action[];
  setActions: (a: Action[]) => void;
}

const ACT: Record<Action, { label: string; key: string; Icon: typeof Hourglass }> = {
  charge: { label: "Carregar", key: "C", Icon: ArrowDownToLine },
  discharge: { label: "Descarregar", key: "D", Icon: ArrowUpFromLine },
  wait: { label: "Esperar", key: "E", Icon: Hourglass },
};
const STATE_TXT = { good: "de les més baixes del dia", warn: "en la mitjana del dia", bad: "de les més altes del dia" };

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
    if (e.c < 1) return "La bateria ja era plena: no hi cabia res més. Una pila plena no aprofita les hores bones.";
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

export default function DecisionGame({ day, bat, actions, setActions }: Props) {
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
  const fc = [...Array(6).keys()].map((k) => h + 1 + k).filter((k) => k < 24);

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
            <div className="sit-hour">{day.hours[h]}</div>
            <dl className="sit-facts">
              <div><dt>CO₂ de la xarxa</dt><dd>{fmt.gCo2(day.co2[h])}<small>/kWh</small></dd>
                <span className={`chip ${tercile(day.co2, day.co2[h])}`}>{STATE_TXT[tercile(day.co2, day.co2[h])]}</span></div>
              <div><dt>Preu</dt><dd>{fmt.dec(day.price[h], 3)}<small> €/kWh</small></dd>
                <span className={`chip ${tercile(day.price, day.price[h])}`}>{STATE_TXT[tercile(day.price, day.price[h])]}</span></div>
              <div><dt>Bateria</dt><dd>{fmt.int(socPct)}<small> %</small></dd>
                <span className="meter"><span style={{ width: `${socPct}%` }} /></span></div>
              <div><dt>Consum ara</dt><dd>{fmt.int(net[h])}<small> kW</small></dd></div>
            </dl>

            <p className="label">Quina decisió prens?</p>
            <div className="choices">
              {(Object.keys(ACT) as Action[]).map((a) => {
                const { label, key, Icon } = ACT[a];
                return (
                  <button key={a} className={`choice ${a}`} onClick={() => decide(a)}>
                    <Icon size={22} aria-hidden /><span>{label}</span><kbd>{key}</kbd>
                  </button>
                );
              })}
            </div>

            {fc.length > 0 && (
              <div className="forecast">
                <p className="label">Previsió de les properes hores</p>
                <table>
                  <thead><tr><th />{fc.map((k) => <th key={k}>{day.hours[k]}</th>)}</tr></thead>
                  <tbody>
                    <tr><td>g CO₂</td>{fc.map((k) => <td key={k} className={tercile(day.co2, day.co2[k])}>{Math.round(day.co2[k] * 1000)}</td>)}</tr>
                    <tr><td>c€/kWh</td>{fc.map((k) => <td key={k} className={tercile(day.price, day.price[k])}>{fmt.dec(day.price[k] * 100, 1)}</td>)}</tr>
                  </tbody>
                </table>
                <p className="fine">Al repte real l'agent només té previsions, amb error. Aquí la previsió és perfecta.</p>
              </div>
            )}
          </section>
        ) : (
          <section className="situation done">
            <div className="sit-hour">24:00</div>
            <p className="done-title">Has gestionat el campus durant un dia sencer.</p>
            <p>Has sumat <b>{fmt.pts(st.total)} punts</b> en decisions. Al nivell 3 veuràs la puntuació oficial, que també té en compte amb quina càrrega acabes el dia, i la compararàs amb les estratègies de l'equip.</p>
            <a className="btn-solid" href="#analitza">Analitza la teva estratègia</a>
          </section>
        )}

        <section className="verdict">
          <div className="score-total">
            <p className="label">Punts de les decisions</p>
            <div className={`score-big ${st.total >= 0 ? "pos" : "neg"}`}>{fmt.pts(st.total)}</div>
            <p className="fine">{h}/24 hores decidides · puntuació orientativa hora a hora; l'oficial és al nivell 3.</p>
          </div>

          {last ? (
            <div className={`last ${last.pts > 0.05 ? "pos" : last.pts < -0.05 ? "neg" : "zero"}`}>
              <p className="label">{day.hours[last.h]} · La teva decisió</p>
              <p className="last-act">{ACT[last.a].label}</p>
              <p className="last-pts">Resultat: <b>{fmt.pts(last.pts)} punts</b></p>
              <p className="last-why"><b>Explicació. </b>{explain(day, bat, last)}</p>
            </div>
          ) : (
            <div className="last zero">
              <p className="label">Com es juga</p>
              <p className="last-why">Comences a mitjanit amb la bateria al {fmt.int((100 * bat.soc0) / bat.cap)} %. Cada hora decideixes si carregues ({fmt.int(bat.pmax)} kW), descarregues o esperes. Els punts mesuren quant redueixes el CO₂ (70 %) i el cost (30 %) del dia.</p>
              <p className="fine">Pista: fixa't en la previsió. L'hora més valuosa per descarregar acostuma a arribar al vespre.</p>
            </div>
          )}

          <div className="btn-row">
            <button className="btn-line" disabled={!h} onClick={() => setActions(actions.slice(0, -1))}><Undo2 size={16} /> Desfés</button>
            <button className="btn-line" disabled={!h} onClick={() => setActions([])}><RotateCcw size={16} /> Torna a començar</button>
          </div>
        </section>
      </div>
    </div>
  );
}
