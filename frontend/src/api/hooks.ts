import { useEffect, useState, useCallback } from "react";
import type { AgentCatalog, DayListItem, DayData, ModelDayResult, CompareResult, Mode, RollingHorizonResult, ScenarioParams } from "./types";

const API = "/api";

export function useAgents() {
  const [catalog, setCatalog] = useState<AgentCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    fetch(`${API}/agents`).then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((data: AgentCatalog) => setCatalog(data)).catch((e) => setError(String(e))).finally(() => setLoading(false));
  }, []);
  return { agents: catalog?.agents ?? [], defaultMode: catalog?.default_mode ?? "dificil", loading, error };
}

// ---------------------------------------------------------------------------
// GET /api/days
// ---------------------------------------------------------------------------

export type { Mode };

export function useDays(mode: Mode, month?: number, year?: number) {
  const [days, setDays] = useState<DayListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({ mode });
    if (month) params.set("month", String(month));
    if (year) params.set("year", String(year));

    fetch(`${API}/days?${params}`)
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(setDays)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [mode, month, year]);

  return { days, loading, error };
}

// ---------------------------------------------------------------------------
// GET /api/day
// ---------------------------------------------------------------------------

export function useDay(date: string, mode: Mode) {
  const [day, setDay] = useState<DayData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!date) { setDay(null); return; }
    setLoading(true);
    setError(null);
    fetch(`${API}/day?date=${date}&mode=${mode}`)
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(setDay)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [date, mode]);

  return { day, loading, error };
}

// ---------------------------------------------------------------------------
// POST /api/model-day
// ---------------------------------------------------------------------------

export function useModelDay() {
  const [result, setResult] = useState<ModelDayResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback((date: string, mode: Mode) => {
    setLoading(true);
    setError(null);
    setResult(null);
    fetch(`${API}/model-day`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date, mode }),
    })
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(setResult)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return { result, loading, error, run };
}

// ---------------------------------------------------------------------------
// POST /api/compare
// ---------------------------------------------------------------------------

export function useCompare() {
  const [result, setResult] = useState<CompareResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback((date: string, mode: Mode, userActions: (string | number)[]) => {
    setLoading(true);
    setError(null);
    setResult(null);
    fetch(`${API}/compare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date, mode, userActions }),
    })
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(setResult)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);
  const reset = useCallback(() => setResult(null), []);

  return { result, loading, error, run, reset };
}
// ---------------------------------------------------------------------------
// POST /api/rolling-horizon (debounced, cancels the previous request)
// ---------------------------------------------------------------------------

export interface RhRequest {
  date: string;
  mode: Mode;
  scenario: Partial<ScenarioParams>;
  nSamples: number;
  activeSeed?: number;
}

export function useRollingHorizon(req: RhRequest | null, debounceMs = 350) {
  const [result, setResult] = useState<RollingHorizonResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const key = req ? JSON.stringify(req) : "";

  useEffect(() => {
    if (!key) return;
    const ctrl = new AbortController();
    const id = setTimeout(() => {
      setLoading(true);
      setError(null);
      const t0 = performance.now();
      fetch(`${API}/rolling-horizon`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: key,
        signal: ctrl.signal,
      })
        .then(async (r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}: ${(await r.text()).slice(0, 200)}`);
          return r.json();
        })
        .then((j: RollingHorizonResult) => { setResult(j); setMs(Math.round(performance.now() - t0)); })
        .catch((e) => { if (e.name !== "AbortError") setError(String(e)); })
        .finally(() => { if (!ctrl.signal.aborted) setLoading(false); });
    }, debounceMs);
    return () => { clearTimeout(id); ctrl.abort(); };
  }, [key, debounceMs]);

  const [ms, setMs] = useState<number | null>(null);
  return { result, loading, error, ms };
}
