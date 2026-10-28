// Tiny fetch wrapper: throws with the server's message so the UI can show it.
async function get(path, params = {}) {
  const qs = new URLSearchParams(params).toString();
  const res = await fetch(`/api${path}${qs ? `?${qs}` : ""}`);
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch { /* ignore */ }
    throw new Error(msg);
  }
  return res.json();
}

export const api = {
  health: () => get("/health"),
  forecastVsActual: (p) => get("/forecast-vs-actual", p),
  metrics: (p) => get("/metrics", p),
  dayAhead: (p) => get("/day-ahead", p),
};
