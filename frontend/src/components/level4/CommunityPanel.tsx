import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Cpu, Lightbulb, MonitorOff, ThermometerSun } from "lucide-react";
import { AXIS, C, fmt } from "../../theme";
import type { DayData } from "../../types";

const LECTIVE_DAYS = 180; // supòsit divulgatiu: dies lectius en un curs

/** Nivell 4: què passa si la comunitat universitària també canvia hàbits. */
export default function CommunityPanel({ day }: { day: DayData }) {
  const dirtiest = day.co2.indexOf(Math.max(...day.co2.slice(14)));
  const [start, setStart] = useState(Math.max(14, dirtiest - 1));
  const [len, setLen] = useState(3);
  const [pct, setPct] = useState(5);

  const hrs = [...Array(len).keys()].map((k) => start + k).filter((h) => h < 24);
  const r = useMemo(() => {
    const kwh = hrs.reduce((a, h) => a + (pct / 100) * day.demand[h], 0);
    const co2 = hrs.reduce((a, h) => a + (pct / 100) * day.demand[h] * day.co2[h], 0);
    const eur = hrs.reduce((a, h) => a + (pct / 100) * day.demand[h] * day.price[h], 0);
    return { kwh, co2, eur };
  }, [hrs, pct, day]);

  const bat = day.totals;
  const extraCo2 = (100 * r.co2) / Math.max(1, bat.co2SavedKg);
  const extraEur = (100 * r.eur) / Math.max(1, bat.costSavedEur);

  const minD = Math.min(...day.demand);
  const meanD = day.totals.demandKwh / 24;
  const baseShare = (100 * minD) / meanD;
  const rows = day.hours.map((h, i) => ({ hour: h, v: day.demand[i], sel: hrs.includes(i) }));

  return (
    <div className="community">
      <div className="comm-grid">
        <section className="comm-sim">
          <p className="label">Escenari real · {day.label.toLowerCase()}</p>
          <p className="comm-q">I si la comunitat reduís el consum un <b>{pct} %</b> de les <b>{day.hours[start]}</b> a les <b>{day.hours[Math.min(23, start + len - 1)].slice(0, 2)}:59</b>?</p>

          <label className="slider"><span>Reducció</span>
            <input type="range" min={1} max={20} value={pct} onChange={(e) => setPct(+e.target.value)} /><output>{pct} %</output></label>
          <label className="slider"><span>A partir de</span>
            <input type="range" min={0} max={23} value={start} onChange={(e) => setStart(+e.target.value)} /><output>{day.hours[start]}</output></label>
          <label className="slider"><span>Durant</span>
            <input type="range" min={1} max={8} value={len} onChange={(e) => setLen(+e.target.value)} /><output>{len} h</output></label>

          <div className="comm-out">
            <div><span className="big">+{fmt.int(extraCo2)} %</span><span>més CO₂ evitat que amb la bateria sola ({fmt.int(r.co2)} kg addicionals)</span></div>
            <div><span className="big">+{fmt.int(extraEur)} %</span><span>més estalvi econòmic ({fmt.eur(r.eur)} addicionals)</span></div>
          </div>
          <p className="fine">
            {fmt.int(r.kwh)} kWh menys avui. Si es repetís els {LECTIVE_DAYS} dies lectius d'un curs, serien unes
            {" "}{fmt.dec((r.co2 * LECTIVE_DAYS) / 1000, 1)} t de CO₂. És un ordre de magnitud: cada dia és diferent.
          </p>
        </section>

        <section className="comm-base">
          <p className="label">El consum de fons</p>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={rows} margin={{ top: 8, right: 4, bottom: 0, left: 0 }} barCategoryGap={2}>
              <CartesianGrid stroke={C.grid} vertical={false} />
              <XAxis dataKey="hour" tick={AXIS} interval={3} tickLine={false} axisLine={{ stroke: C.ink }} />
              <YAxis tick={AXIS} unit=" kW" width={64} tickLine={false} axisLine={false} />
              <Tooltip cursor={{ fill: "rgba(0,0,0,.05)" }} formatter={(v) => [`${fmt.int(Number(v))} kW`, "Consum"]} />
              <ReferenceLine y={minD} stroke={C.ink} strokeDasharray="4 3"
                label={{ value: `mínim ${fmt.int(minD)} kW`, position: "insideBottomLeft", fill: C.ink, fontSize: 11 }} />
              <Bar dataKey="v" isAnimationActive={false}>
                {rows.map((r) => <Cell key={r.hour} fill={r.sel ? C.green : "#C9C7BE"} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <p className="note">
            Fins i tot a l'hora més tranquil·la, el campus consumeix el <b>{fmt.int(baseShare)} %</b> del consum mitjà.
            Una part és imprescindible (servidors, laboratoris, ventilació) i una altra poden ser equips que
            ningú no ha apagat. Distingir-les demana una auditoria, però és un marge que cap bateria no pot resoldre.
            En verd, les hores del teu escenari.
          </p>
        </section>
      </div>

      <div className="actions">
        <div><MonitorOff size={22} aria-hidden /><b>Apaga en marxar</b><p>Ordinadors, pantalles i equips de laboratori que queden encesos de nit alimenten el consum de fons.</p></div>
        <div><ThermometerSun size={22} aria-hidden /><b>Climatització a les hores vermelles</b><p>Un grau menys de fred o de calor al vespre redueix el consum quan l'electricitat és més bruta.</p></div>
        <div><Cpu size={22} aria-hidden /><b>Càlculs pesats a les hores verdes</b><p>Simulacions, entrenaments de models i còpies de seguretat es poden programar al migdia.</p></div>
        <div><Lightbulb size={22} aria-hidden /><b>Llum natural</b><p>Les aules buides amb els llums encesos són energia que ni el sol ni la bateria poden compensar.</p></div>
      </div>
    </div>
  );
}
