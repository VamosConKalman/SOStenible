import { fmt } from "../../theme";
import type { DashboardData } from "../../types";

export function AnnualBanner({ data }: { data: DashboardData }) {
  const a = data.annual;
  return (
    <section className="annual" aria-label="Balanç de l'any">
      <p className="annual-lead">En {a.nDays} dies amb dades completes, la bateria gestionada de manera òptima hauria evitat</p>
      <div className="annual-figs">
        <div><b>{fmt.dec(a.co2SavedKg / 1000)} t</b><span>de CO₂ ({fmt.dec(a.co2SavedPct)} %)</span></div>
        <div><b>{fmt.eur(a.costSavedEur)}</b><span>de factura ({fmt.dec(a.costSavedPct)} %)</span></div>
        <div><b>{fmt.int(a.co2SavedKg / data.equivalences.kgCo2PerTreeYear)}</b><span>arbres absorbint CO₂ un any</span></div>
      </div>
    </section>
  );
}

export default function Methodology({ data }: { data: DashboardData }) {
  const b = data.battery, e = data.equivalences;
  return (
    <footer id="metode" className="method">
      <div className="method-inner">
        <h2>Com ho calculem</h2>
        <div className="method-grid">
          <div>
            <h3>Dades</h3>
            <p>Comptador fiscal del Campus Nord i els 3 inversors de la planta solar (cada 5 min, agregats per hores), preu PVPC i intensitat de carboni del mix peninsular. Període {data.generatedFrom}.</p>
          </div>
          <div>
            <h3>Algorisme</h3>
            <p>Optimització lineal de 24 h: puntuació = {data.weights.co2} × ΔCO₂ % + {data.weights.cost} × Δcost %. Bateria de {fmt.int(b.capacityKwh)} kWh, {fmt.int(b.powerKw)} kW i {b.efficiency * 100} % de rendiment, sense abocar a xarxa i acabant al {b.socInit * 100} %.</p>
          </div>
          <div>
            <h3>Equivalències</h3>
            <p>{e.kgCo2PerKmCar * 1000} g CO₂/km de cotxe, {e.kgCo2PerTreeYear} kg CO₂/any per arbre adult, {e.kwhPerPhoneCharge * 1000} Wh per càrrega de mòbil. Són ordres de magnitud, no xifres de precisió.</p>
          </div>
        </div>
        <div className="method-foot">
          <img src={`${import.meta.env.BASE_URL}brand/upc-sostenible.png`} alt="UPC Sostenible" />
          <p>Datathon UPC Sostenible 2026 · Campus Nord · Universitat Politècnica de Catalunya · BarcelonaTech</p>
        </div>
      </div>
    </footer>
  );
}
