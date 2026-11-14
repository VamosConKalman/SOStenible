import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { fmt, tercile } from "../theme";
import type { DashboardData, DayData } from "../types";

export interface Fact { title: string; body: string }

/** Píndoles "Sabies que...?" calculades amb les dades del dia triat. */
export function buildFacts(data: DashboardData, day: DayData): Record<"system" | "battery" | "market" | "people", Fact[]> {
  const b = data.battery;
  const meanDemand = day.totals.demandKwh / 24;
  const minDemand = Math.min(...day.demand);
  const hoursFull = b.capacityKwh / b.powerKw;
  const mismatch = day.price.filter((p, h) => tercile(day.price, p) !== tercile(day.co2, day.co2[h])).length;
  const cheapIdx = day.price.indexOf(Math.min(...day.price));
  const cleanIdx = day.co2.indexOf(Math.min(...day.co2));

  return {
    system: [
      { title: "El sol del campus és petit", body: `Les plaques del Campus Nord han cobert avui el ${fmt.dec(day.totals.solarShare)} % del consum. Gairebé tota l'electricitat arriba de la xarxa.` },
      { title: "El campus no dorm mai del tot", body: `A l'hora més tranquil·la del dia el campus encara demana ${fmt.int(minDemand)} kW, el ${fmt.int((100 * minDemand) / meanDemand)} % del consum mitjà.` },
    ],
    battery: [
      { title: "Una bateria no crea energia", body: "Només la canvia d'hora: la guarda quan l'electricitat és neta i barata, i la torna quan és bruta i cara." },
      { title: "Carregar i descarregar té pèrdues", body: `El rendiment és del ${fmt.int(b.efficiency * 100)} %: de cada 10 kWh que entren, en surten 9. Per això no val la pena moure energia entre hores semblants.` },
      { title: "La Pila Gigant té límits", body: `Hi caben ${fmt.int(b.capacityKwh)} kWh i no pot carregar ni descarregar més de ${fmt.int(b.powerKw)} kW. Omplir-la del tot costa com a mínim ${fmt.dec(hoursFull / b.efficiency)} hores.` },
      { title: "2 MWh no és tant", body: `Amb la bateria plena, el campus funcionaria uns ${fmt.int((b.capacityKwh / meanDemand) * 60)} minuts. No serveix per desconnectar-se: serveix per triar bé les hores.` },
    ],
    market: [
      { title: "Barat no sempre vol dir net", body: `Avui l'hora més barata ha estat les ${day.hours[cheapIdx]} i la més neta les ${day.hours[cleanIdx]}. En ${mismatch} de les 24 hores, el preu i el CO₂ no estaven al mateix nivell (barat, intermedi o car).` },
      { title: "El migdia peninsular és solar", body: "Quan fa sol a tot l'Estat, les plaques solars de tota la península abaixen el CO₂ de la xarxa, encara que al campus no en sobri." },
    ],
    people: [
      { title: "La tecnologia sola no n'hi ha prou", body: `La bateria ha estalviat avui ${fmt.int(day.totals.co2SavedKg)} kg de CO₂. Una petita reducció del consum a les hores brutes pot sumar-hi tant o més.` },
    ],
  };
}

export default function DidYouKnow({ facts, tone = "light" }: { facts: Fact[]; tone?: "light" | "green" }) {
  const [i, setI] = useState(0);
  if (!facts.length) return null;
  const f = facts[i % facts.length];
  return (
    <aside className={`dyk dyk-${tone}`} aria-live="polite">
      <div className="dyk-tag">Sabies que…?</div>
      <div className="dyk-body">
        <strong>{f.title}</strong>
        <p>{f.body}</p>
      </div>
      {facts.length > 1 && (
        <div className="dyk-nav">
          <button aria-label="Anterior" onClick={() => setI((i + facts.length - 1) % facts.length)}><ChevronLeft size={18} /></button>
          <span>{(i % facts.length) + 1}/{facts.length}</span>
          <button aria-label="Següent" onClick={() => setI(i + 1)}><ChevronRight size={18} /></button>
        </div>
      )}
    </aside>
  );
}
