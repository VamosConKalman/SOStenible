import { useMemo, useState } from "react";
import {
  Area, ComposedChart, Line, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { AXIS, C, fmt } from "../../theme";
import type { DayData } from "../../types";

const SERIES = [
  { key: "solar", name: "Sol del campus", color: C.solar },
  { key: "battery", name: "Bateria → edificis", color: C.battery },
  { key: "gridDirect", name: "Xarxa elèctrica", color: C.grid_ },
  { key: "toBattery", name: "Entra a la bateria", color: C.charge },
] as const;

/** Mur d'energia: d'on ve, hora a hora, l'electricitat dels edificis. */
export default function EnergyWall({ day, hour }: { day: DayData; hour: number }) {
  const [table, setTable] = useState(false);
  const rows = useMemo(() => day.hours.map((h, i) => {
    const solar = Math.min(day.solar[i], day.demand[i]);
    const battery = day.discharge[i];
    return { hour: h, solar, battery, gridDirect: Math.max(0, day.demand[i] - solar - battery),
      toBattery: -day.charge[i], demand: day.demand[i] };
  }), [day]);

  return (
    <div className="block">
      <div className="block-head">
        <div>
          <h3>El mur d'energia: d'on ve l'electricitat que gastem a classe?</h3>
          <p className="lead">Cada color és una font. La línia negra és el que demanen els edificis. Per sota del zero, el que entra a la bateria.</p>
        </div>
        <button className="btn-line" onClick={() => setTable((t) => !t)}>{table ? "Gràfic" : "Taula de dades"}</button>
      </div>

      <ul className="legend">
        {SERIES.map((s) => <li key={s.key}><i style={{ background: s.color }} />{s.name}</li>)}
        <li><i className="line" />Consum dels edificis</li>
      </ul>

      {table ? (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Hora</th><th>Consum</th><th>Sol</th><th>Bateria → edificis</th><th>Xarxa</th><th>Entra a la bateria</th><th>Bateria</th></tr></thead>
            <tbody>{rows.map((r, i) => (
              <tr key={r.hour} className={i === hour ? "on" : ""}>
                <td>{r.hour}</td><td>{fmt.int(r.demand)}</td><td>{fmt.int(r.solar)}</td><td>{fmt.int(r.battery)}</td>
                <td>{fmt.int(r.gridDirect)}</td><td>{fmt.int(-r.toBattery)}</td><td>{fmt.int(day.soc[i])} %</td>
              </tr>))}
            </tbody>
          </table>
          <p className="fine">kW, mitjana de cada hora.</p>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={360}>
          <ComposedChart data={rows} margin={{ top: 22, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={C.grid} vertical={false} />
            <XAxis dataKey="hour" tick={AXIS} interval={2} tickLine={false} axisLine={{ stroke: C.ink }} />
            <YAxis tick={AXIS} tickLine={false} axisLine={false} unit=" kW" width={66} />
            <ReferenceLine y={0} stroke={C.ink} />
            <ReferenceLine x={day.hours[hour]} stroke={C.ink} strokeDasharray="2 3"
              label={{ value: day.hours[hour], position: "top", fill: C.ink, fontSize: 12, fontWeight: 700 }} />
            <Tooltip content={<Tip />} />
            {SERIES.slice(0, 3).map((s) => (
              <Area key={s.key} type="stepAfter" dataKey={s.key} stackId="s" stroke="#fff" strokeWidth={1}
                fill={s.color} fillOpacity={1} isAnimationActive={false} />
            ))}
            <Area type="stepAfter" dataKey="toBattery" stackId="b" stroke="#fff" strokeWidth={1}
              fill={C.charge} fillOpacity={1} isAnimationActive={false} />
            <Line type="stepAfter" dataKey="demand" stroke={C.ink} strokeWidth={2} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function Tip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="tip">
      <b>{label}</b>
      <span><i style={{ background: C.ink }} />Consum {fmt.int(p.demand)} kW</span>
      <span><i style={{ background: C.solar }} />Sol {fmt.int(p.solar)} kW</span>
      <span><i style={{ background: C.battery }} />Bateria → edificis {fmt.int(p.battery)} kW</span>
      <span><i style={{ background: C.grid_ }} />Xarxa {fmt.int(p.gridDirect)} kW</span>
      {p.toBattery < 0 && <span><i style={{ background: C.charge }} />Entra a la bateria {fmt.int(-p.toBattery)} kW</span>}
    </div>
  );
}
