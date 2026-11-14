export interface DayData {
  id: string;
  date: string;          // AAAA-MM-DD
  weekday: number;       // 0 = dilluns … 6 = diumenge
  solarIdx: number;      // sol del dia / dia molt assolellat del mateix mes
  activityIdx: number;   // consum del dia / mediana dels laborables del mes
  hours: string[];
  demand: number[];      // kW
  solar: number[];       // kW
  price: number[];       // €/kWh
  co2: number[];         // kg CO2/kWh
  charge: number[];      // kW que entren a la bateria (estratègia òptima)
  discharge: number[];   // kW que surten de la bateria
  soc: number[];         // % estat de càrrega al final de cada hora
  totals: {
    demandKwh: number;
    solarKwh: number;
    solarShare: number;
    co2BaseKg: number;
    co2OptKg: number;
    co2SavedKg: number;
    costBaseEur: number;
    costOptEur: number;
    costSavedEur: number;
    shiftedKwh: number;
  };
}

export interface DashboardData {
  generatedFrom: string;
  battery: { capacityKwh: number; powerKw: number; efficiency: number; socInit: number };
  weights: { co2: number; cost: number };
  equivalences: { kgCo2PerKmCar: number; kgCo2PerTreeYear: number; kwhPerPhoneCharge: number };
  days: DayData[];
  annual: {
    nDays: number;
    co2SavedKg: number;
    co2SavedPct: number;
    costSavedEur: number;
    costSavedPct: number;
    solarMwh: number;
    demandMwh: number;
  };
}
