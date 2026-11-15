// Types matching the backend API responses
export interface DayListItem {
  date: string;
  label: string;
  weekday: number;
  solarIdx: number;
  activityIdx: number;
}

export interface DayData {
  date: string;
  hours: string[];
  demand: number[];
  solar: number[];
  price: number[];
  co2: number[];
  units: Record<string, string>;
}

export interface ModelDayResult {
  actions: string[];        // "carga" | "descarga" | "espera"
  power: number[];           // kW signed
  soc: number[];             // kWh start of each hour
  soc_final: number;
  grid: number[];            // kW imported
  score: number;
  dCO2: number;
  dCost: number;
  infracciones: number;
}

export interface HourlyCompare {
  h: number;
  user: string;
  model: string;
  userKw: number;
  modelKw: number;
  userPts: number;
  modelPts: number;
}

export interface ScoreDetail {
  dCO2: number;
  dCost: number;
  infracciones: number;
}

export interface CompareResult {
  userScore: number;
  modelScore: number;
  user: ScoreDetail;
  model: ScoreDetail;
  hourly: HourlyCompare[];
  diagnosis: string[];
}

export type Mode = "estandar" | "dificil";

export interface AgentOption { id: Mode; label: string; description: string; score_reference: number | null; capacity_kwh: number; power_kw: number; forecast_horizon: number; }
export interface AgentCatalog { default_mode: Mode; agents: AgentOption[]; }

export const MODE_LABELS: Record<Mode, string> = {
  estandar: "Estàndard",
  dificil: "Difícil (LASSO)",
};

export const MODE_DESC: Record<Mode, string> = {
  estandar: "Bateria 2 MWh, ±500 kW, preus i CO2 completament coneguts.",
  dificil: "Bateria 6 MWh, ±1.500 kW, només 3 h de previsió de preu/CO2 + meteo.",
};
// ---------------------------------------------------------------------------
// POST /api/rolling-horizon
// ---------------------------------------------------------------------------

export interface ScenarioParams {
  demand_scale: number; demand_noise: number;
  solar_scale: number; solar_noise: number;
  price_scale: number; price_noise: number;
  co2_scale: number; co2_noise: number;
  persistence: number;
  cloud_start: number; cloud_hours: number; cloud_depth: number;
  shock_start: number; shock_hours: number; shock_kw: number;
  cut_start: number; cut_hours: number;
  seed: number;
}

type Num = number | null;

export interface RhStep {
  t: number;
  soc0: number;          // kWh at the start of the hour
  P: number;             // kW decided (+ charge / − discharge)
  seenPrices: number;    // hours of price/CO2 the agent actually sees
  meas: [number, number] | null;   // last measured load and solar (t−1)
  H: number;             // LP horizon
  w: Num[] | null;       // weights ×1000 (forecast)
  V: number;
  c: Num[] | null; d: Num[] | null;  // planned charge / discharge (kW)
  soc: Num[] | null;     // planned SOC, H+1 points starting at t
  net: Num[] | null;     // net load used by the LP (with safety margin)
  netRaw: Num[] | null;  // net load forecast without margin
  priceFc: Num[] | null; co2Fc: Num[] | null;
}

export interface RhDayArrays {
  hours: string[];
  load: number[]; pv: number[]; net: number[];
  price: number[]; co2: number[]; w: number[];
}

export interface RhRunSummary {
  score: number; dCO2: number; dCost: number; infracciones: number; soc_final: number;
  socPath: number[]; applied: number[]; oracle: number; oracleSoc: number[];
}

export interface RhEnsembleItem {
  seed: number; score: number; dCO2: number; dCost: number; infracciones: number;
  soc_final: number; oracle: number; socPath: number[];
}

export interface RollingHorizonResult {
  mode: Mode;
  battery: { capacityKwh: number; powerKw: number; forecastHours: number };
  scenario: ScenarioParams;
  activeSeed: number;
  stochastic: boolean;      // false: no random noise, a single scenario is returned
  real: RhDayArrays;
  day: RhDayArrays;
  baseline: RhRunSummary;
  active: RhRunSummary & { grid: number[]; ptsPerHour: number[]; oraclePower: number[] };
  steps: RhStep[];
  leadError: { k: number; mae: number; n: number }[];
  ensemble: RhEnsembleItem[];
}
