import { fmt } from "../../theme";
import type { DashboardData, DayData } from "../../types";

/** Tres xifres compactes perquè la secció 1 càpiga en una pantalla. */
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
        <div className="kpi-row"><span className="kpi-num">{fmt.dec(t.solarShare)}<small>%</small></span>
          <span className="kpi-txt">de l'electricitat ve de les plaques del campus</span></div>
        <div className="bar" role="img" aria-label={`Sol ${fmt.dec(t.solarShare)} %, bateria ${fmt.dec(batShare)} %, xarxa la resta`}>
          <span className="b-solar" style={{ width: `${t.solarShare}%` }} />
          <span className="b-bat" style={{ width: `${batShare}%` }} />
        </div>
      </article>
      <article className="kpi">
        <p className="label">CO₂ evitat aquest dia</p>
        <div className="kpi-row"><span className="kpi-num">{fmt.int(t.co2SavedKg)}<small>kg</small></span>
          <span className="kpi-txt">≈ {fmt.int(km)} km de cotxe o {fmt.int(trees)} arbres durant un any</span></div>
      </article>
      <article className="kpi">
        <p className="label">Estalvi a la factura</p>
        <div className="kpi-row"><span className="kpi-num">{fmt.int(t.costSavedEur)}<small>€</small></span>
          <span className="kpi-txt">{fmt.int(t.shiftedKwh)} kWh canviats d'hora per la bateria</span></div>
      </article>
    </div>
  );
}
