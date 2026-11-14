import { fmt } from "../../theme";
import type { DashboardData, DayData } from "../../types";

/** Tres xifres grans, amb lectura quotidiana. */
export default function KpiStrip({ data, day }: { data: DashboardData; day: DayData }) {
  const t = day.totals;
  const eq = data.equivalences;
  const batShare = (100 * t.shiftedKwh) / t.demandKwh;
  const km = t.co2SavedKg / eq.kgCo2PerKmCar;
  const trees = Math.max(1, t.co2SavedKg / eq.kgCo2PerTreeYear);

  return (
    <div className="kpis">
      <article className="kpi">
        <p className="label">Autosuficiència del dia</p>
        <div className="kpi-num">{fmt.dec(t.solarShare)}<small>%</small></div>
        <p>de l'electricitat l'han produït les plaques del campus.</p>
        <div className="bar" role="img" aria-label={`Sol ${fmt.dec(t.solarShare)} %, bateria ${fmt.dec(batShare)} %`}>
          <span className="b-solar" style={{ width: `${t.solarShare}%` }} />
          <span className="b-bat" style={{ width: `${batShare}%` }} />
        </div>
        <ul className="key">
          <li><i className="b-solar" />Sol {fmt.dec(t.solarShare)} %</li>
          <li><i className="b-bat" />Des de la bateria {fmt.dec(batShare)} %</li>
          <li><i className="b-grid" />Xarxa</li>
        </ul>
      </article>

      <article className="kpi">
        <p className="label">CO₂ evitat avui</p>
        <div className="kpi-num">{fmt.int(t.co2SavedKg)}<small>kg</small></div>
        <p>gràcies a la bateria, un {fmt.dec((100 * t.co2SavedKg) / t.co2BaseKg)} % menys.</p>
        <dl className="equiv">
          <div><dt>{fmt.int(km)} km</dt><dd>de cotxe que no s'han fet</dd></div>
          <div><dt>{fmt.int(trees)} arbres</dt><dd>absorbint CO₂ durant un any</dd></div>
        </dl>
      </article>

      <article className="kpi">
        <p className="label">Factura</p>
        <div className="kpi-num">{fmt.int(t.costSavedEur)}<small>€</small></div>
        <p>menys d'electricitat comprada a la xarxa avui.</p>
        <dl className="equiv">
          <div><dt>{fmt.int(t.demandKwh / 1000)} MWh</dt><dd>consumits pel campus en 24 h</dd></div>
          <div><dt>{fmt.int(t.shiftedKwh)} kWh</dt><dd>canviats d'hora per la bateria</dd></div>
        </dl>
      </article>
    </div>
  );
}
