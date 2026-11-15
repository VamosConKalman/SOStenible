"""
agent.py — BatteryAgent para el Modo Difícil (MPC + LP HiGHS + previsiones).

Cada hora:
  1. Guarda lo observado: precio y CO2 de las horas que da el obs (3 h) y la medida de t-1.
  2. Prevé precio y CO2 de t+3..t+23 (ayer a la misma hora + perfiles de train con nivel actual),
     y la carga neta N = consumo − solar de t..t+23 (perfil + persistencia del residuo; solar con
     envolvente de cielo claro × índice de claridad que persiste).
  3. Resuelve un LP de 24 h con la restricción de importación g_k ≥ N̂_k + c_k − d_k en todas las horas
     y aplica solo la decisión de la hora actual, recortada a los límites físicos del obs.
Sin red, sin ficheros en act(): perfiles y parámetros se leen en __init__.
"""
from __future__ import annotations

import datetime
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

import lp_model as lp
import features as FE

ONE_HOUR = pd.Timedelta(hours=1)
DAY = pd.Timedelta(hours=24)


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


class BatteryAgent:
    def __init__(self):
        path = Path(__file__).parent
        self.p = {
            "kappa": 0.5973, "w_co2": 0.7, "w_cost": 0.3, "eps": 0.5, "delta": 1e-6,
            "H": 24, "alpha_ayer": 0.0, "rho_nivel": 0.97, "peso_nivel_ahora": 1.0, "beta_ayer_load": 0.0,
            "z_net": 0.5, "sd_net0": 100.0, "sd_net_k": 5.0, "terminal_q": None,
            "corte": True, "e_max": 6000.0, "p_max": 1500.0,
            "peso_online_solar": 0.0,   # OnlineSolarCorrection: 0 = ruta original exacta
            "alpha_online_solar": 0.25, "max_bias_solar": 0.20, "max_err_solar": 0.30,
            "tau_online_solar": 6.0, "min_muestras_solar": 3,
            "estocastico": False,
            "tiempo_max_s": 40.0,  # seguro: con más tiempo acumulado en act(), pasa al determinista  # LP en dos etapas con los escenarios de perfils.json["esc"]
            "mezcla": 0.0,         # peso de las reglas en un promedio con el LASSO (0 = solo LASSO)
            "lasso_net": True,     # carga neta con LASSO (False = reglas)
            "lasso_precios": True, # precio y CO2 con LASSO (False = reglas)
            "lasso": True,         # previsiones LASSO (perfils.json["lasso"]) si existen
            "modelo": False,       # usar los modelos lineales mod_* de perfils.json si existen
            "week_hours": 168,    # si es un número: el bloque acaba week_hours después de su primera hora
        }
        try:
            self.p.update(json.loads((path / "parametres.json").read_text()))
        except Exception:
            pass
        self.prof = None
        try:
            P = json.loads((path / "perfils.json").read_text())
            self.prof = {k: (np.asarray(v, dtype=np.float64) if isinstance(v, list) else v) for k, v in P.items()}
            self.prof["phi_load"] = float(P.get("phi_load", 0.9)); self.prof["phi_kt"] = float(P.get("phi_kt", 0.8))
            if "esc" in P:
                self.prof["esc"] = (np.asarray(P["esc"]["centros"], dtype=np.float64),
                                    np.asarray(P["esc"]["probs"], dtype=np.float64))
            if "lasso" in P:
                self.prof["lasso"] = {v: (np.asarray(d["coef"], dtype=np.float64), np.asarray(d["b"], dtype=np.float64))
                                      for v, d in P["lasso"].items()}
            if "kappa" in P and "kappa" not in json.loads((path / "parametres.json").read_text() or "{}"):
                self.p["kappa"] = float(P["kappa"])
        except Exception:
            self.prof = None
        self._px = {}        # ts -> (precio, co2) observados
        self._meas = {}      # ts (inicio de hora medida) -> (load, pv)
        self._last_ts = None
        self._block_start = None
        self.n_fail = 0
        self.n_cortes = 0
        self.last_info = {}
        self.oracle = None
        self.rec = None      # SOLO pruebas locales: lista donde se guardan (ts, N̂ sin margen)
        self._net_raw = None
        self.n_estoc_fail = 0
        # OnlineSolarCorrection: error del LASSO ORIGINAL (sin corregir) en la claridad de la hora actual
        self._kt_h0 = None        # (ts, kt previsto por el LASSO para ts, sin corrección)
        self._sol_bias = 0.0
        self._sol_n = 0
        self._sol_date = None
        self._t_total = 0.0   # SOLO para pruebas locales: dict con Series 'price', 'co2', 'net'

    # ------------------------------------------------------------------
    def act(self, obs):
        t0 = datetime.datetime.now()
        try:
            return float(self._act(obs))
        except Exception:
            self.n_fail += 1
            return 0.0
        finally:
            self._t_total += (datetime.datetime.now() - t0).total_seconds()

    # ------------------------------------------------------------------
    def _clim(self, key, ts):
        return float(self.prof[key][ts.month - 1, int(ts.dayofweek >= 5), ts.hour])

    def _remember(self, ts, preus, co2s, meas):
        for i in range(min(len(preus), len(co2s))):
            self._px[ts + i * ONE_HOUR] = (preus[i], co2s[i])
        if meas is not None:
            self._meas[ts - ONE_HOUR] = meas
        lim = ts - 2 * DAY
        if len(self._px) > 80:
            self._px = {k: v for k, v in self._px.items() if k >= lim}
        if len(self._meas) > 80:
            self._meas = {k: v for k, v in self._meas.items() if k >= lim}

    def _forecast_prices(self, ts, preus, co2s, H):
        n = min(len(preus), len(co2s))
        out_p, out_c = np.empty(H), np.empty(H)
        if self.prof is None:
            # sin perfiles: repetir el último valor conocido
            for k in range(H):
                out_p[k] = preus[min(k, n - 1)]; out_c[k] = co2s[min(k, n - 1)]
            return out_p, out_c
        cp = np.array([self._clim("price", ts + k * ONE_HOUR) for k in range(H)])
        cc = np.array([self._clim("co2", ts + k * ONE_HOUR) for k in range(H)])
        lp_ = np.mean(preus[:n]) / max(np.mean(cp[:n]), 1e-6)
        lc_ = np.mean(co2s[:n]) / max(np.mean(cc[:n]), 1e-6)
        g = self.p["peso_nivel_ahora"]
        if g < 1.0:
            sp = sc = cp24 = cc24 = 0.0
            for h, (pv_, cv_) in self._px.items():
                if ts - DAY <= h < ts:
                    sp += pv_; sc += cv_
                    cp24 += self._clim("price", h); cc24 += self._clim("co2", h)
            if cp24 > 0 and cc24 > 0:
                lp_ = g * lp_ + (1 - g) * sp / cp24
                lc_ = g * lc_ + (1 - g) * sc / cc24
        lp_ = float(np.clip(lp_, 0.4, 2.5)); lc_ = float(np.clip(lc_, 0.4, 2.5))
        a, rho = self.p["alpha_ayer"], self.p["rho_nivel"]
        for k in range(H):
            if k < n:
                out_p[k], out_c[k] = preus[k], co2s[k]
                continue
            dec = rho ** (k - n + 1)
            fp = cp[k] * (1 + (lp_ - 1) * dec)
            fc = cc[k] * (1 + (lc_ - 1) * dec)
            y = self._px.get(ts + k * ONE_HOUR - DAY)
            if y is not None:
                fp = a * y[0] + (1 - a) * fp
                fc = a * y[1] + (1 - a) * fc
            out_p[k], out_c[k] = fp, fc
        return out_p, out_c

    def _forecast_net(self, ts, meas, H):
        if self.prof is None:
            return None
        hrs = [ts + k * ONE_HOUR for k in range(H)]
        load = np.array([self._clim("load", h) for h in hrs])
        env = np.array([self._clim("pv_env", h) for h in hrs])
        ktm = float(self.prof["kt_mean"][ts.month - 1])
        # residuo de consumo de la última medida válida
        if meas is not None:
            r = meas[0] - self._clim("load", ts - ONE_HOUR)
            load = load + r * self.prof["phi_load"] ** np.arange(1, H + 1)
        b = self.p["beta_ayer_load"]
        if b > 0:
            for k, h in enumerate(hrs):
                y = self._meas.get(h - DAY)
                if y is not None and y[0] > 0:
                    load[k] = b * y[0] + (1 - b) * load[k]
        # claridad: última hora de sol medida (hoy) o media de ayer
        kt_now = None
        if meas is not None:
            e1 = self._clim("pv_env", ts - ONE_HOUR)
            if e1 > 100:
                kt_now = meas[1] / e1
        if kt_now is None:
            vals = []
            for h, (l, pv) in self._meas.items():
                if ts - DAY <= h < ts:
                    e = self._clim("pv_env", h)
                    if e > 100:
                        vals.append(pv / e)
            if vals:
                kt_now = float(np.mean(vals))
        kt = np.full(H, ktm)
        if kt_now is not None:
            kt = ktm + (min(max(kt_now, 0.0), 1.3) - ktm) * self.prof["phi_kt"] ** np.arange(1, H + 1)
        pv = env * np.clip(kt, 0.0, 1.3)
        net = load - pv
        z = self.p["z_net"]
        if z:
            net = net - z * (self.p["sd_net0"] + self.p["sd_net_k"] * np.arange(H))
        return net

    # ------------------------------------------------------------------
    def _forecast_model(self, ts, preus, co2s, meas, H):
        """Precio, CO2 y carga neta con los modelos directos por (k, hora destino)."""
        Mp, Mc, Ml, Mk = (self.prof[k] for k in ("mod_p", "mod_c", "mod_l", "mod_k"))
        n = min(len(preus), len(co2s))
        hrs = [ts + k * ONE_HOUR for k in range(H)]
        cp = np.array([self._clim("price", h) for h in hrs]); cc = np.array([self._clim("co2", h) for h in hrs])
        ap = [preus[min(j, n - 1)] / max(self._clim("price", ts + j * ONE_HOUR), 1e-6) - 1 for j in range(3)]
        ac = [co2s[min(j, n - 1)] / max(self._clim("co2", ts + j * ONE_HOUR), 1e-6) - 1 for j in range(3)]
        mc, dc = float(np.mean(ac)), ac[2] - ac[0]
        pr, cr = np.empty(H), np.empty(H)
        for k, h in enumerate(hrs):
            if k < n:
                pr[k], cr[k] = preus[k], co2s[k]
                continue
            y = self._px.get(h - DAY)
            yp = y[0] / max(self._clim("price", h - DAY), 1e-6) - 1 if y else 0.0
            yc = y[1] / max(self._clim("co2", h - DAY), 1e-6) - 1 if y else 0.0
            has = 1.0 if y else 0.0
            kk = min(k, 23)
            pr[k] = cp[k] * (1 + float(Mp[kk, h.hour] @ np.array([1, ap[0], ap[1], ap[2], yp, has])))
            cr[k] = cc[k] * (1 + float(Mc[kk, h.hour] @ np.array([1, ac[0], ac[1], ac[2], yc, has])))
        pr = np.maximum(pr, 1e-4); cr = np.maximum(cr, 1e-4)

        # consumo
        l1 = meas[0] - self._clim("load", ts - ONE_HOUR) if meas is not None else 0.0
        load = np.empty(H)
        for k, h in enumerate(hrs):
            y = self._meas.get(h - DAY)
            ly = y[0] - self._clim("load", h - DAY) if (y and y[0] > 0) else 0.0
            f = np.array([1, l1, ly, 1.0 if (y and y[0] > 0) else 0.0, mc])
            load[k] = self._clim("load", h) + float(Ml[min(k, 23), h.hour] @ f)
        # solar: claridad
        ktm = float(self.prof["kt_mean"][ts.month - 1])
        lk, has_lk, best = 0.0, 0.0, None
        for hh, (l, pv) in self._meas.items():
            if ts - DAY <= hh < ts:
                e = self._clim("pv_env", hh)
                if e > 100 and (best is None or hh > best):
                    best, lk, has_lk = hh, pv / e - ktm, 1.0
        pv = np.empty(H)
        for k, h in enumerate(hrs):
            e = self._clim("pv_env", h)
            if e <= 1e-6:
                pv[k] = 0.0
                continue
            y = self._meas.get(h - DAY)
            ey = self._clim("pv_env", h - DAY)
            if y and ey > 100:
                ky, hy = y[1] / ey - ktm, 1.0
            else:
                ky, hy = 0.0, 0.0
            f = np.array([1, lk, has_lk, ky, hy, mc, dc])
            kt = ktm + float(Mk[min(k, 23), h.hour] @ f)
            pv[k] = e * min(max(kt, 0.0), 1.3)
        net = load - pv
        z = self.p["z_net"]
        if z:
            net = net - z * (self.p["sd_net0"] + self.p["sd_net_k"] * np.arange(H))
        return pr, cr, net

    # ------------------------------------------------------------------
    def _update_online_solar(self, ts, meas, corte):
        """EWMA del error de claridad del LASSO original en la hora anterior (reinicio diario)."""
        prev = ts - ONE_HOUR
        if self._sol_date != prev.date():            # nuevo día: reiniciar antes de usar observaciones
            self._sol_date, self._sol_bias, self._sol_n = prev.date(), 0.0, 0
        saved, self._kt_h0 = self._kt_h0, None
        if saved is None or saved[0] != prev or meas is None or corte or self.prof is None:
            return
        e_env = self._clim("pv_env", prev)
        if e_env <= 100:
            return
        mx = float(self.p["max_err_solar"]); mb = float(self.p["max_bias_solar"])
        err = min(max(meas[1] / e_env - saved[1], -mx), mx)
        a = float(self.p["alpha_online_solar"])
        self._sol_bias = min(max((1 - a) * self._sol_bias + a * err, -mb), mb)
        self._sol_n += 1

    # ------------------------------------------------------------------
    def _forecast_lasso(self, ts, preus, co2s, meas, met, H):
        L = self.prof["lasso"]
        n = min(len(preus), len(co2s))
        hrs = [ts + k * ONE_HOUR for k in range(H)]
        clim = lambda key, h: self._clim(key, h)
        ap = np.array([[preus[min(j, n - 1)] / max(clim("price", ts + j * ONE_HOUR), 1e-6) - 1 for j in range(3)]] * H)
        ac = np.array([[co2s[min(j, n - 1)] / max(clim("co2", ts + j * ONE_HOUR), 1e-6) - 1 for j in range(3)]] * H)
        ktm_of = lambda h: float(self.prof["kt_mean"][h.month - 1])
        # medida de t-1
        if meas is not None:
            l1, hl1 = meas[0] - clim("load", ts - ONE_HOUR), 1.0
        else:
            l1, hl1 = 0.0, 0.0
        # última claridad de día en las 24 h previas
        lk, hlk, best = 0.0, 0.0, None
        for hh, (l, pv) in self._meas.items():
            if ts - DAY <= hh < ts:
                e = clim("pv_env", hh)
                if e > 100 and (best is None or hh > best):
                    best, lk, hlk = hh, pv / e - ktm_of(hh), 1.0
        # ayer (τ-24)
        ly, hly, ky, hky, py, cy, hpc = (np.zeros(H) for _ in range(7))
        for k, h in enumerate(hrs):
            y = self._meas.get(h - DAY)
            if y is not None and y[0] > 0:
                ly[k], hly[k] = y[0] - clim("load", h - DAY), 1.0
                e = clim("pv_env", h - DAY)
                if e > 100:
                    ky[k], hky[k] = y[1] / e - ktm_of(h - DAY), 1.0
            q = self._px.get(h - DAY)
            if q is not None:
                py[k] = q[0] / max(clim("price", h - DAY), 1e-6) - 1
                cy[k] = q[1] / max(clim("co2", h - DAY), 1e-6) - 1
                hpc[k] = 1.0
        hm = 1.0 if met is not None else 0.0
        irr, tamb, tpan, vent = met if met is not None else (0.0, 0.0, 0.0, 0.0)
        env = np.array([clim("pv_env", h) for h in hrs])
        X = FE.build(np.array([h.hour for h in hrs], dtype=float),
                     np.array([float(h.dayofweek >= 5) for h in hrs]), np.array([float(h.month) for h in hrs]),
                     ap, ac, np.full(H, l1), np.full(H, hl1), np.full(H, lk), np.full(H, hlk),
                     ly, hly, ky, hky, py, cy, hpc,
                     np.full(H, irr), np.full(H, tamb), np.full(H, tpan), np.full(H, vent), np.full(H, hm), env)
        kk = np.minimum(np.arange(H), L["l"][0].shape[0] - 1)     # más allá de 24 h: coeficientes del último horizonte
        pred = {v: np.einsum("kf,kf->k", X, L[v][0][kk]) + L[v][1][kk] for v in L}
        load = np.array([clim("load", h) for h in hrs]) + pred["l"]
        ktm = np.array([ktm_of(h) for h in hrs])
        lam = float(self.p["peso_online_solar"])
        if lam > 0:
            kt_lasso = np.clip(ktm + pred["k"], 0.0, 1.3)
            self._kt_h0 = (ts, float(kt_lasso[0])) if env[0] > 100 else None
            corr = np.zeros(H)
            if (self._sol_n >= int(self.p["min_muestras_solar"]) and self._sol_date == ts.date()):
                k = np.arange(H)
                mismo_dia = np.array([h.date() == ts.date() for h in hrs])
                corr = np.where(mismo_dia & (env > 100),
                                lam * self._sol_bias * np.exp(-k / float(self.p["tau_online_solar"])), 0.0)
            pv = env * np.clip(kt_lasso + corr, 0.0, 1.3)
        else:
            pv = env * np.clip(ktm + pred["k"], 0.0, 1.3)
        net = load - pv
        self._net_raw = net.copy()
        z = self.p["z_net"]
        if z:
            net = net - z * (self.p["sd_net0"] + self.p["sd_net_k"] * np.arange(H))
        pr = np.array([clim("price", h) for h in hrs]) * (1 + pred["p"])
        cr = np.array([clim("co2", h) for h in hrs]) * (1 + pred["c"])
        pr[:n] = preus[:min(n, H)]; cr[:n] = co2s[:min(n, H)]
        return np.maximum(pr, 1e-4), np.maximum(cr, 1e-4), net

    # ------------------------------------------------------------------
    def _act(self, obs):
        self._net_raw = None
        ts = pd.Timestamp(obs["timestamp"])
        soc = float(obs["soc_kwh"])
        e_max = _num(obs.get("cap_max_kwh")) or self.p["e_max"]
        p_max = _num(obs.get("power_max_kw")) or self.p["p_max"]
        preus = [float(x) for x in obs.get("preus_properes_24h", [])][:24]
        co2s = [float(x) for x in obs.get("co2_properes_24h", [])][:24]
        n = min(len(preus), len(co2s))
        if n == 0:
            return 0.0

        # medida de t-1 (solo si es la hora consecutiva y viene completa)
        meas = None
        prev, self._last_ts = self._last_ts, ts
        if prev is None or ts - prev != ONE_HOUR:
            self._block_start = ts            # primera hora de un bloque nuevo (salto en el tiempo)
        nd = obs.get("noves_dades_5min")
        if prev is not None and ts - prev == ONE_HOUR and isinstance(nd, dict):
            l, pv = _num(nd.get("ultim_consum_kw")), _num(nd.get("ultima_solar_kw"))
            if l is not None and pv is not None:
                meas = (l, pv)
        corte = meas is not None and meas[0] == 0.0 and meas[1] == 0.0
        if float(self.p["peso_online_solar"]) > 0:
            self._update_online_solar(ts, meas, corte)
        met = None
        if meas is not None and isinstance(nd, dict):
            vals = [_num(nd.get(k)) for k in ("irradiancia_wm2", "temp_ambient_c", "temp_panel_c", "vent_ms")]
            if all(v is not None for v in vals):
                met = tuple(vals)
        self._remember(ts, preus, co2s, None if (meas is None or corte) else meas)

        # horizonte: 24 h salvo que los vectores avisen de fin de datos
        H = int(self.p["H"]) if n >= 3 else n
        is_end = n < 3
        wh = self.p["week_hours"]
        if wh:
            left = int((self._block_start + (int(wh) - 1) * ONE_HOUR - ts) / ONE_HOUR) + 1
            if left >= 1 and left <= H:
                H, is_end = left, True

        use_mod = False
        if bool(self.p["lasso"]) and self.prof is not None and "lasso" in self.prof:
            pm, cm, nm = self._forecast_lasso(ts, preus, co2s, None if corte else meas, met, H)
            use_mod = bool(np.isfinite(pm).all() and np.isfinite(cm).all() and np.isfinite(nm).all())
            if not use_mod:
                self._net_raw = None
        elif bool(self.p["modelo"]) and self.prof is not None and "mod_p" in self.prof:
            use_mod = True
        if use_mod and not bool(self.p["lasso"]):
            pm, cm, nm = self._forecast_model(ts, preus, co2s, None if corte else meas, H)
            if not (np.isfinite(pm).all() and np.isfinite(cm).all() and np.isfinite(nm).all()):
                use_mod = False      # salvaguarda: si algo sale no finito, reglas simples
        if self.oracle is not None and "price" in self.oracle:
            idx = [ts + k * ONE_HOUR for k in range(H)]
            pr = self.oracle["price"].reindex(idx).ffill().to_numpy()
            cr = self.oracle["co2"].reindex(idx).ffill().to_numpy()
        elif use_mod and (self.p["lasso_precios"] or not self.p["lasso"]):
            pr, cr = pm, cm
        else:
            pr, cr = self._forecast_prices(ts, preus, co2s, H)
        w = self.p["w_co2"] * cr + self.p["w_cost"] * self.p["kappa"] * pr

        if self.oracle is not None and "net" in self.oracle:
            net = self.oracle["net"].reindex([ts + k * ONE_HOUR for k in range(H)]).to_numpy()
        elif use_mod and (self.p["lasso_net"] or not self.p["lasso"]):
            net = nm
        else:
            net = self._forecast_net(ts, None if corte else meas, H)
        if corte and self.p["corte"]:
            if net is None:
                net = np.full(H, np.inf)
            net = np.array(net, dtype=np.float64)
            net[0] = 0.0
            self.n_cortes += 1

        m = float(self.p["mezcla"])
        if m > 0 and use_mod and bool(self.p["lasso"]) and self.oracle is None:
            pr_r, cr_r = self._forecast_prices(ts, preus, co2s, H)
            net_r = self._forecast_net(ts, None if corte else meas, H)
            pr = (1 - m) * pr + m * pr_r
            cr = (1 - m) * cr + m * cr_r
            if net_r is not None:
                net0 = net[0]
                net = (1 - m) * net + m * net_r
                if corte and self.p["corte"]:
                    net[0] = net0
            w = self.p["w_co2"] * cr + self.p["w_cost"] * self.p["kappa"] * pr

        V = 0.0
        q = self.p["terminal_q"]
        if q is not None and not is_end:
            V = lp.ETA_D * float(np.quantile(w, q))

        if self.rec is not None and self._net_raw is not None:
            self.rec.append((ts, self._net_raw.copy()))
        P = None
        if (self.p["estocastico"] and self._t_total < self.p["tiempo_max_s"]
                and self.prof is not None and "esc" in self.prof
                and self._net_raw is not None and self.oracle is None):
            try:
                cen, pr_s = self.prof["esc"]
                hh = ts.hour
                kk = np.minimum(np.arange(H), cen.shape[2] - 1)
                nets = self._net_raw[None, :H] + cen[hh][:, kk]
                if corte and self.p["corte"]:
                    nets[:, 0] = 0.0
                r = lp.solve_lp_stoch(w, soc, nets, pr_s[hh], eps=self.p["eps"], delta=self.p["delta"],
                                      p_max=p_max, e_max=e_max)
                if r is not None:
                    P = r[0] - r[1]
                else:
                    self.n_estoc_fail += 1
            except Exception:
                self.n_estoc_fail += 1
        if P is None:   # determinista (y plan B del estocástico)
            x = lp.solve_lp(w, soc, V, net=net, eps=self.p["eps"], delta=self.p["delta"], p_max=p_max, e_max=e_max)
            P = 0.0 if x is None else float(x[0] - x[H])
        P = lp.clamp(P, soc, p_max, e_max, self.p["eps"])
        self.last_info = {"H": H, "V": V, "P": P}
        return P
