// Tria del dia per dia i mes, i frase que el descriu a partir de les dades.
import type { DayData } from "../types";

export const MONTHS = ["gener", "febrer", "març", "abril", "maig", "juny", "juliol", "agost",
  "setembre", "octubre", "novembre", "desembre"];

const doy = (m: number, d: number) => new Date(Date.UTC(2001, m - 1, d)).getTime() / 864e5;

/** Dia de les dades amb el mateix dia i mes; si no n'hi ha, el més proper del calendari. */
export function findDay(days: DayData[], month: number, dayOfMonth: number) {
  const target = doy(month, dayOfMonth);
  let best = days[0], bestDist = Infinity;
  for (const d of days) {
    const [, m, dd] = d.date.split("-").map(Number);
    const raw = Math.abs(doy(m, dd) - target);
    const dist = Math.min(raw, 365 - raw);
    if (dist < bestDist) { bestDist = dist; best = d; }
  }
  return { day: best, exact: bestDist === 0 };
}

export function daysInMonth(month: number) {
  return [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
}

const SEASON = (m: number) =>
  m === 12 || m <= 2 ? "d'hivern" : m <= 5 ? "de primavera" : m <= 8 ? "d'estiu" : "de tardor";

/** Frase curta (títol) i frase explicativa del tipus de dia. */
export function describeDay(d: DayData) {
  const month = Number(d.date.slice(5, 7));
  const weekend = d.weekday >= 5;
  const holiday = !weekend && (d.activityIdx < 0.85 || month === 8);
  const sky = d.solarIdx >= 0.85 ? "assolellat" : d.solarIdx >= 0.55 ? "amb núvols i clarianes" : "ennuvolat";
  const kind = weekend ? "Cap de setmana" : holiday ? "Dia festiu o de vacances" : "Dia de classe";
  const title = `${kind} ${sky} ${SEASON(month)}`;

  let text: string;
  if (weekend) text = "Els edificis estan gairebé buits: el que es veu és sobretot el consum de fons.";
  else if (holiday) text = "Campus a mig gas: hi ha menys activitat que en un dia lectiu normal.";
  else if (d.solarIdx >= 0.85) text = "Molta activitat docent i de recerca, i bona producció de les plaques solars.";
  else text = "Els edificis treballen a ple rendiment, però les plaques produeixen poc.";
  if (month === 12 || month <= 2) text += " Dies curts: poques hores de sol.";
  return { title, text };
}

export function longDate(iso: string) {
  return new Intl.DateTimeFormat("ca-ES", { weekday: "long", day: "numeric", month: "long", year: "numeric" })
    .format(new Date(iso + "T12:00:00"));
}
