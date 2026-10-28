import { useEffect, useMemo, useState } from "react";
import {
  Area, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, LineChart,
  ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "./api.js";

const MW = (v) => (v == null ? "–" : `${Math.round(v).toLocaleString("en-GB")} MW`);
const tick = (iso) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)} ${iso.slice(11, 16)}` : "");
const C = { actual: "#0f766e", forecast: "#f97316", band: "#fdba74", mae: "#2563eb", rmse: "#7c3aed" };

function useAsync(fn, deps) {
  const [s, set] = useState({ loading: true, data: null, error: null });
  useEffect(() => {
    let live = true;
    set((p) => ({ ...p, loading: true, error: null }));
    fn().then((data) => live && set({ loading: false, data, error: null }))
        .catch((error) => live && set({ loading: false, data: null, error: error.message }));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return s;
}

const Card = ({ label, value, hint }) => (
  <div className="kpi"><div className="kpi-label">{label}</div><div className="kpi-value">{value}</div>
    {hint && <div className="kpi-hint">{hint}</div>}</div>
);

const Section = ({ title, sub, children, state }) => (
  <section className="panel">
    <h2>{title}</h2>{sub && <p className="sub">{sub}</p>}
    {state?.error ? <div className="err">Could not load: {state.error}</div>
      : state?.loading && !state.data ? <div className="muted">Loading…</div> : children}
  </section>
);

export default function App() {
  const [start, setStart] = useState("2026-01-01");
  const [end, setEnd] = useState("2026-01-31");
  const [horizon, setHorizon] = useState(24);
  const [day, setDay] = useState("2026-01-15");
  const [cutoff, setCutoff] = useState(10);

  const health = useAsync(() => api.health(), []);
  const fva = useAsync(() => api.forecastVsActual({ start, end, horizon }), [start, end, horizon]);
  const met = useAsync(() => api.metrics({ start, end, horizon }), [start, end, horizon]);
  const da = useAsync(() => api.dayAhead({ delivery_date: day, cutoff_hour: cutoff }), [day, cutoff]);

  const m = met.data?.summary;
  const daRows = useMemo(() => (da.data?.rows || []).map((r) => ({ ...r, range: [r.low, r.high] })), [da.data]);

  return (
    <div className="page">
      <header>
        <div>
          <h1>Wind Forecast Monitor</h1>
          <p className="muted">GB national wind generation · Elexon BMRS (WINDFOR forecasts vs FUELHH actuals) · January 2026 · all times UTC</p>
        </div>
        {health.data?.source === "sample" && <span className="badge warn">SYNTHETIC SAMPLE DATA</span>}
      </header>

      <div className="controls">
        <label>From <input type="date" value={start} min="2026-01-01" max={end} onChange={(e) => setStart(e.target.value)} /></label>
        <label>To <input type="date" value={end} min={start} max="2026-01-31" onChange={(e) => setEnd(e.target.value)} /></label>
        <label className="grow">Forecast lead time: <b>{horizon} h</b> before delivery
          <input type="range" min="0" max="48" value={horizon} onChange={(e) => setHorizon(+e.target.value)} />
        </label>
      </div>

      <div className="kpis">
        <Card label="MAE" value={MW(m?.mae)} hint="avg absolute error" />
        <Card label="RMSE" value={MW(m?.rmse)} hint="penalises big misses" />
        <Card label="Bias" value={m ? `${m.bias > 0 ? "+" : ""}${Math.round(m.bias).toLocaleString("en-GB")} MW` : "–"}
              hint={m ? (m.bias > 0 ? "over-forecast → risk of being short" : "under-forecast → risk of over-buying") : ""} />
        <Card label="WAPE" value={m?.wape_pct != null ? `${m.wape_pct.toFixed(1)}%` : "–"} hint="MAE ÷ mean actual" />
        <Card label="P90 abs. error" value={MW(m?.p90_abs)} hint="9 in 10 hours are within this" />
        <Card label="Hours compared" value={m?.n ?? "–"} />
      </div>

      <Section title="Forecast vs actual" state={fva}
        sub={`For each hour, the latest forecast published at least ${horizon} h earlier is compared with what was actually generated.`}>
        <ResponsiveContainer width="100%" height={340}>
          <LineChart data={fva.data?.rows || []}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="startTime" tickFormatter={tick} minTickGap={60} />
            <YAxis tickFormatter={(v) => `${v / 1000}k`} label={{ value: "MW", angle: -90, position: "insideLeft" }} />
            <Tooltip labelFormatter={tick} formatter={(v) => MW(v)} />
            <Legend />
            <Line type="monotone" dataKey="actual" name="Actual" stroke={C.actual} dot={false} strokeWidth={2} isAnimationActive={false} />
            <Line type="monotone" dataKey="forecast" name="Forecast" stroke={C.forecast} dot={false} strokeWidth={2} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </Section>

      <div className="two">
        <Section title="Error vs lead time" state={met}
          sub="The earlier you must decide, the worse the forecast. Dashed line = lead time selected above.">
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={met.data?.by_horizon || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="horizon_h" label={{ value: "hours before delivery", position: "insideBottom", offset: -4 }} />
              <YAxis tickFormatter={(v) => `${v / 1000}k`} />
              <Tooltip formatter={(v) => MW(v)} labelFormatter={(h) => `${h} h ahead`} />
              <Legend verticalAlign="top" />
              <ReferenceLine x={horizon} stroke="#6b7280" strokeDasharray="4 4" />
              <Line dataKey="mae" name="MAE" stroke={C.mae} dot={false} strokeWidth={2} isAnimationActive={false} />
              <Line dataKey="rmse" name="RMSE" stroke={C.rmse} dot={false} strokeWidth={2} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </Section>
        <Section title="Error by hour of day" state={met} sub="Mean absolute error at the selected lead time.">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={met.data?.by_hour || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="hour" /><YAxis tickFormatter={(v) => `${v / 1000}k`} />
              <Tooltip formatter={(v) => MW(v)} labelFormatter={(h) => `${h}:00 UTC`} />
              <Bar dataKey="mae" name="MAE" fill={C.mae} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </Section>
      </div>

      <Section title="Day-ahead decision view" state={da}
        sub="What the desk would have seen at decision time: the latest forecast published before the cut-off, with an 80% uncertainty band learned from past forecast errors.">
        <div className="controls inner">
          <label>Delivery day <input type="date" value={day} min="2026-01-01" max="2026-01-31" onChange={(e) => setDay(e.target.value)} /></label>
          <label>Decision time (D-1)
            <select value={cutoff} onChange={(e) => setCutoff(+e.target.value)}>
              {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00 UTC</option>)}
            </select>
          </label>
          {da.data && <span className="muted">Using forecasts published up to <b>{tick(da.data.decision_time)}</b></span>}
        </div>
        {da.data && (
          <div className="kpis small">
            <Card label="Expected wind (avg)" value={MW(da.data.summary.mean_forecast)} />
            <Card label="Plan for (avg, 80% range)" value={`${Math.round(da.data.summary.mean_low).toLocaleString("en-GB")} – ${Math.round(da.data.summary.mean_high).toLocaleString("en-GB")} MW`}
                  hint={da.data.band.basis === "earlier_days" ? `band from ${da.data.band.n_days} earlier days` : `band from ${da.data.band.n_days} other days (little history)`} />
            <Card label="Peak / min forecast" value={`${Math.round(da.data.summary.peak_forecast).toLocaleString("en-GB")} / ${Math.round(da.data.summary.min_forecast).toLocaleString("en-GB")}`} />
            <Card label="How it turned out (MAE)" value={da.data.summary.backtest ? MW(da.data.summary.backtest.mae) : "n/a"} hint="forecast vs actual that day" />
          </div>
        )}
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={daRows}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="startTime" tickFormatter={(v) => v.slice(11, 16)} />
            <YAxis tickFormatter={(v) => `${v / 1000}k`} />
            <Tooltip labelFormatter={tick} formatter={(v) => (Array.isArray(v) ? `${Math.round(v[0])} – ${Math.round(v[1])} MW` : MW(v))} />
            <Legend />
            <Area dataKey="range" name="80% band" stroke="none" fill={C.band} fillOpacity={0.5} isAnimationActive={false} />
            <Line dataKey="forecast" name="Forecast at decision time" stroke={C.forecast} dot={false} strokeWidth={2} isAnimationActive={false} />
            <Line dataKey="actual" name="Actual" stroke={C.actual} dot={false} strokeWidth={2} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </Section>

      <footer className="muted">
        Error = forecast − actual (positive = wind over-forecast). Actuals are hourly means of the 30-minute FUELHH values.
        Source: Elexon BMRS. Wind only; no demand or price data is used.
      </footer>
    </div>
  );
}
