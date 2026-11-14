// Identitat: blau UPC (Pantone 3005) + verd UPC Sostenible (pres del logotip).
// La paleta de dades s'ha validat per contrast i daltonisme.
export const C = {
  upc: "#007BC0",
  upcDark: "#004E7A",
  green: "#58A532",     // verd UPC Sostenible (logotip)
  greenDark: "#3E8E2A",
  ink: "#141414",
  ink2: "#4B4B4B",
  muted: "#8A8A85",
  rule: "#141414",
  grid: "#E2E0D8",
  paper: "#F5F4EE",

  // sèries
  solar: "#E0A100",
  grid_: "#007BC0",
  battery: "#3E8E2A",
  charge: "#8A5CC2",

  // estats
  good: "#3E8E2A",
  warn: "#D98A00",
  bad: "#C8372D",
};

export const fmt = {
  int: (v: number) => Math.round(v).toLocaleString("ca-ES"),
  dec: (v: number, d = 1) =>
    v.toLocaleString("ca-ES", { minimumFractionDigits: d, maximumFractionDigits: d }),
  eur: (v: number) =>
    v.toLocaleString("ca-ES", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }),
  gCo2: (kgPerKwh: number) => `${Math.round(kgPerKwh * 1000)} g`,
  cKwh: (eurPerKwh: number) =>
    `${(eurPerKwh * 100).toLocaleString("ca-ES", { maximumFractionDigits: 1 })} c€`,
  pts: (v: number) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toLocaleString("ca-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}`,
};

/** Classifica un valor en terços (net/barat · intermedi · brut/car) respecte al dia. */
export function tercile(values: number[], v: number): "good" | "warn" | "bad" {
  const s = [...values].sort((a, b) => a - b);
  const lo = s[Math.floor(s.length / 3)];
  const hi = s[Math.floor((2 * s.length) / 3)];
  return v <= lo ? "good" : v >= hi ? "bad" : "warn";
}

export const AXIS = { fill: C.muted, fontSize: 12, fontFamily: "Arial, sans-serif" };
