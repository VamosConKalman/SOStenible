// Lògica compartida: simulació de la bateria, puntuació oficial del repte i
// diagnòstic de decisions. Mateixes regles que starter_kit/common.py:
// puntuació = 0,7·ΔCO2 % + 0,3·Δcost %, sense exportar a xarxa.
import type { DashboardData, DayData } from "../types";

export type Action = "charge" | "discharge" | "wait";

export interface Battery { cap: number; pmax: number; eta: number; soc0: number }

export const batteryOf = (d: DashboardData): Battery => ({
  cap: d.battery.capacityKwh,
  pmax: d.battery.powerKw,
  eta: d.battery.efficiency,
  soc0: d.battery.socInit * d.battery.capacityKwh,
});

/** Càrrega neta (sense bateria) i referència de CO2 i cost del dia. */
export function baseline(day: DayData) {
  const net = day.demand.map((v, h) => Math.max(0, v - day.solar[h]));
  const co2 = net.reduce((a, v, h) => a + v * day.co2[h], 0);
  const cost = net.reduce((a, v, h) => a + v * day.price[h], 0);
  return { net, co2, cost };
}

/** Pes d'un kWh importat a l'hora h, en "punts del repte" (per 100). */
export function hourWeights(day: DayData, wCo2 = 0.7, wCost = 0.3) {
  const b = baseline(day);
  return day.co2.map((c, h) => 100 * (wCo2 * c / b.co2 + wCost * day.price[h] / b.cost));
}

/** Aplica una acció d'una hora; retorna l'energia moguda i el nou estat de càrrega. */
export function step(bat: Battery, soc: number, net: number, a: Action) {
  if (a === "charge") {
    const c = Math.min(bat.pmax, (bat.cap - soc) / bat.eta);
    return { c, d: 0, soc: soc + bat.eta * c, limited: c < bat.pmax - 1 };
  }
  if (a === "discharge") {
    const d = Math.min(bat.pmax, soc, net);
    return { c: 0, d, soc: soc - d, limited: d < Math.min(bat.pmax, net) - 1 };
  }
  return { c: 0, d: 0, soc, limited: false };
}

export interface RunResult {
  soc: number[]; grid: number[]; c: number[]; d: number[];
  co2Kg: number; costEur: number; co2SavedKg: number; costSavedEur: number;
  dCo2: number; dCost: number; score: number;
}

/** Avalua una sèrie d'accions (o d'energies de l'LP) amb la puntuació oficial. */
export function evaluate(day: DayData, bat: Battery, c: number[], d: number[]): RunResult {
  const b = baseline(day);
  let soc = bat.soc0;
  const socs: number[] = [], grid: number[] = [];
  for (let h = 0; h < 24; h++) {
    soc = soc + bat.eta * c[h] - d[h];
    socs.push(soc);
    grid.push(b.net[h] + c[h] - d[h]);
  }
  // Regla del dia: la pila ha d'acabar com ha començat (com l'òptim). Si acaba més buida,
  // l'energia que falta es compra a l'hora més cara i bruta del dia (pitjor cas), de manera
  // que cap estratègia pot "guanyar" a l'òptim gastant-se la reserva.
  const debt = Math.max(0, bat.soc0 - soc) / bat.eta;
  const mCo2 = Math.max(...day.co2);
  const mPrice = Math.max(...day.price);
  const co2Kg = grid.reduce((a, v, h) => a + v * day.co2[h], 0) + debt * mCo2;
  const costEur = grid.reduce((a, v, h) => a + v * day.price[h], 0) + debt * mPrice;
  const dCo2 = (100 * (b.co2 - co2Kg)) / b.co2;
  const dCost = (100 * (b.cost - costEur)) / b.cost;
  return { soc: socs, grid, c, d, co2Kg, costEur, co2SavedKg: b.co2 - co2Kg, costSavedEur: b.cost - costEur,
    dCo2, dCost, score: 0.7 * dCo2 + 0.3 * dCost };
}

export function runActions(day: DayData, bat: Battery, actions: Action[]): RunResult {
  const { net } = baseline(day);
  let soc = bat.soc0;
  const c: number[] = [], d: number[] = [];
  for (let h = 0; h < 24; h++) {
    const s = step(bat, soc, net[h], actions[h] ?? "wait");
    c.push(s.c); d.push(s.d); soc = s.soc;
  }
  return evaluate(day, bat, c, d);
}

/** Estratègia heurística: carrega en el terç d'hores més "barates" (preu+CO2) i descarrega en el terç més car. */
export function heuristicActions(day: DayData): Action[] {
  const w = hourWeights(day);
  const s = [...w].sort((a, b) => a - b);
  const lo = s[7], hi = s[16];
  return w.map((v) => (v <= lo ? "charge" : v >= hi ? "discharge" : "wait"));
}

export function optimalRun(day: DayData, bat: Battery) {
  return evaluate(day, bat, day.charge, day.discharge);
}

/** Puntuació immediata d'una decisió (per al joc): guany respecte a esperar. */
export function decisionPoints(day: DayData, bat: Battery, h: number, socBefore: number, a: Action) {
  const w = hourWeights(day);
  const { net } = baseline(day);
  const s = step(bat, socBefore, net[h], a);
  const later = w.slice(h + 1).sort((x, y) => y - x);
  const bestLater = later.slice(0, 3);
  const futureHigh = bestLater.length ? bestLater.reduce((x, y) => x + y, 0) / bestLater.length : 0;
  const mean = w.reduce((x, y) => x + y, 0) / 24;
  let pts = 0;
  if (a === "charge") pts = s.c * (bat.eta * futureHigh - w[h]);
  if (a === "discharge") pts = s.d * (w[h] - Math.max(mean, later[0] ?? 0) * 0.85);
  return { pts, ...s };
}

/** Diagnòstic "Per què?": compara les decisions de l'usuari amb l'òptim. */
export function diagnose(day: DayData, bat: Battery, user: RunResult): string[] {
  const w = hourWeights(day);
  const tips: { gain: number; text: string }[] = [];
  const hh = (h: number) => day.hours[h];
  const cents = (v: number) => (v * 100).toLocaleString("ca-ES", { maximumFractionDigits: 1 });
  const used = new Set<number>();

  // Descàrregues fetes massa aviat: hi havia hores més valuoses més tard i la pila s'hi va quedar buida
  for (let h = 0; h < 24; h++) {
    if (user.d[h] < 50) continue;
    const later = [...Array(24).keys()].filter((k) => k > h && w[k] > w[h] * 1.15 && user.soc[k - 1] < 100 && user.d[k] < bat.pmax - 50);
    if (later.length) {
      const k = later.reduce((a, b) => (w[b] > w[a] ? b : a));
      if (used.has(k)) continue;
      used.add(k);
      tips.push({ gain: (w[k] - w[h]) * user.d[h], text:
        `Has descarregat massa aviat. A les ${hh(k)} hi havia una hora més cara (${cents(day.price[k])} c€/kWh) i més contaminant (${Math.round(day.co2[k] * 1000)} g CO₂/kWh) que a les ${hh(h)}, i la bateria ja hi arribava buida.` });
    }
  }
  // Càrregues en hores cares/brutes quan n'hi havia de més netes abans de fer-la servir
  for (let h = 0; h < 24; h++) {
    if (user.c[h] < 50) continue;
    const better = [...Array(24).keys()].filter((k) => k !== h && Math.abs(k - h) <= 6 && w[k] < w[h] * 0.8);
    if (better.length) {
      const k = better.reduce((a, b) => (w[b] < w[a] ? b : a));
      tips.push({ gain: (w[h] - w[k]) * user.c[h], text:
        `Has carregat a les ${hh(h)} (${Math.round(day.co2[h] * 1000)} g CO₂/kWh, ${cents(day.price[h])} c€/kWh), però a les ${hh(k)} l'electricitat valia menys: ${Math.round(day.co2[k] * 1000)} g i ${cents(day.price[k])} c€/kWh.` });
    }
  }
  if (user.soc[23] < bat.soc0 - 300)
    tips.push({ gain: (bat.soc0 - user.soc[23]) * Math.max(...w) * 0.5, text:
      `Has acabat el dia amb la bateria al ${Math.round((user.soc[23] / bat.cap) * 100)} %, per sota del ${Math.round((bat.soc0 / bat.cap) * 100)} % inicial. Aquesta energia s'ha de reposar i la comptem com si es comprés a l'hora més cara del dia.` });
  // Energia guardada que no es fa servir
  const end = user.soc[23];
  if (end > bat.soc0 + 300)
    tips.push({ gain: (end - bat.soc0) * 0.01, text:
      `Has acabat el dia amb ${Math.round((end / bat.cap) * 100)} % de bateria. Aquesta energia, carregada i no utilitzada, només ha suposat pèrdues (de cada 10 kWh que entren, en surten 9).` });
  // Hores clau no aprofitades
  const top = [...Array(24).keys()].sort((a, b) => w[b] - w[a]).slice(0, 3);
  const missed = top.filter((h) => user.d[h] < 50 && day.discharge[h] > 50 && !used.has(h));
  if (missed.length)
    tips.push({ gain: missed.length, text:
      `No has fet servir la bateria a ${missed.map(hh).join(", ")}, les hores amb l'electricitat més cara i bruta del dia. L'algorisme les reserva per a això.` });

  const out = tips.sort((a, b) => b.gain - a.gain).map((t) => t.text);
  return [...new Set(out)].slice(0, 4);
}
