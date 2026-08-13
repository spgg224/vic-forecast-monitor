import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import "./extras.css";

type Horizon = { horizon_minutes: string; observations: number; mae: number; rmse: number; median_absolute_error: number; bias: number; p95_absolute_error: number };
type Scorecard = { coverage: { start: string; end: string; forecast_vintages: number; target_intervals: number }; overall: Horizon; by_horizon: Horizon[] };
type Vintage = { issue_time: string; horizon_minutes: number; forecast_price: number };
type Event = { issue_time: string; target_time: string; horizon_minutes: number; forecast_price: number; actual_price: number; forecast_error: number; absolute_error: number; vintages: Vintage[] };
type Events = { lead_minutes: number; events: Event[] };
type Findings = { far_to_near_error_ratio: number; top_one_percent_error_share: number; actual_intervals_above_1000: number; max_actual_price: number };

const money = new Intl.NumberFormat("en-AU", { style: "currency", currency: "AUD", maximumFractionDigits: 2 });
const number = new Intl.NumberFormat("en-AU");

function Metric({ label, value, note }: { label: string; value: string; note: string }) {
  return <article className="metric"><span>{label}</span><strong>{value}</strong><small>{note}</small></article>;
}

function HorizonChart({ rows }: { rows: Horizon[] }) {
  const max = Math.max(...rows.map(row => row.mae));
  return <div className="bars" aria-label="Mean absolute error by forecast horizon">{rows.map(row =>
    <div className="barRow" key={row.horizon_minutes}><span>{row.horizon_minutes} min</span><div className="track"><div className="fill" style={{ width: `${row.mae / max * 100}%` }} /></div><b>{money.format(row.mae)}</b></div>
  )}</div>;
}

function ReplayChart({ event }: { event: Event }) {
  const all = [...event.vintages.map(v => v.forecast_price), event.actual_price];
  const min = Math.min(...all), max = Math.max(...all), span = Math.max(1, max - min);
  const points = event.vintages.map((v, i) => `${10 + i * 80 / Math.max(1, event.vintages.length - 1)},${88 - (v.forecast_price - min) / span * 76}`).join(" ");
  const actualY = 88 - (event.actual_price - min) / span * 76;
  return <div className="replay"><svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Forecast revisions and actual price"><line x1="8" x2="94" y1={actualY} y2={actualY} className="actualLine"/><polyline points={points} className="forecastLine"/></svg><div className="legend"><span><i className="blue"/>Forecast revisions</span><span><i className="red"/>Actual {money.format(event.actual_price)}</span></div></div>;
}

function App() {
  const [scores, setScores] = useState<Scorecard | null>(null);
  const [events, setEvents] = useState<Events | null>(null);
  const [findings, setFindings] = useState<Findings | null>(null);
  const [selected, setSelected] = useState<Event | null>(null);
  useEffect(() => {
    Promise.all(["scorecard", "events", "findings"].map(name => fetch(`${import.meta.env.BASE_URL}data/${name}.json`).then(r => r.json())))
      .then(([scoreData, eventData, findingData]) => { setScores(scoreData); setEvents(eventData); setFindings(findingData); setSelected(eventData.events[0]); });
  }, []);
  const dates = useMemo(() => scores ? `${new Date(scores.coverage.start).toLocaleDateString("en-AU")} - ${new Date(scores.coverage.end).toLocaleDateString("en-AU")}` : "Loading", [scores]);
  if (!scores || !events || !findings) return <main className="loading">Loading VIC forecast data...</main>;
  const near = scores.by_horizon[0], far = scores.by_horizon.at(-1)!;
  return <>
    <header><div className="eyebrow">AEMO PUBLIC DATA / HISTORICAL ANALYSIS</div><h1>VIC Forecast Monitor</h1><p>When five-minute electricity price forecasts diverged from market reality.</p><div className="meta"><span>VIC1</span><span>{dates}</span><span>Not a live trading signal</span></div></header>
    <main>
      <section className="metrics">
        <Metric label="Forecast vintages" value={number.format(scores.coverage.forecast_vintages)} note={`${number.format(scores.coverage.target_intervals)} actual intervals`} />
        <Metric label="Overall MAE" value={money.format(scores.overall.mae)} note={`Median ${money.format(scores.overall.median_absolute_error)}`} />
        <Metric label="0-10 min MAE" value={money.format(near.mae)} note="Closest forecast horizon" />
        <Metric label="50-60 min MAE" value={money.format(far.mae)} note={`${findings.far_to_near_error_ratio.toFixed(1)}x near-term error`} />
      </section>
      <section className="grid">
        <article className="panel wide"><div className="panelHead"><div><span className="kicker">FORECAST HORIZON</span><h2>Error grows with forecast distance</h2></div><span className="unit">MAE / $/MWh</span></div><HorizonChart rows={scores.by_horizon} /><p className="caveat">Horizon groups remain separate so later updates are never confused with earlier information.</p></article>
        <article className="panel"><div className="panelHead"><div><span className="kicker">EVENT EXPLORER</span><h2>Largest 30-minute misses</h2></div></div><div className="eventList">{events.events.slice(0, 8).map(event => <button className={selected?.target_time === event.target_time ? "active" : ""} onClick={() => setSelected(event)} key={event.target_time}><span>{new Date(event.target_time).toLocaleString("en-AU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</span><b>{event.forecast_error > 0 ? "+" : ""}{money.format(event.forecast_error)}</b></button>)}</div></article>
        <article className="panel event"><span className="kicker">SELECTED REPLAY</span>{selected && <><h2>{new Date(selected.target_time).toLocaleString("en-AU", { dateStyle: "medium", timeStyle: "short" })}</h2><ReplayChart event={selected}/><div className="comparison"><div><span>30-minute forecast</span><strong>{money.format(selected.forecast_price)}</strong></div><div className="arrow">to</div><div><span>Actual</span><strong>{money.format(selected.actual_price)}</strong></div></div><div className={`miss ${selected.forecast_error < 0 ? "under" : "over"}`}>{selected.forecast_error < 0 ? "Under-forecast" : "Over-forecast"} by {money.format(selected.absolute_error)}</div><p>The line shows how AEMO revised this interval across twelve runs. Rankings use only the vintage nearest a declared 30-minute lead.</p></>}</article>
      </section>
      <section className="findings"><span className="kicker">FULL-YEAR FINDINGS</span><div><p><strong>{findings.far_to_near_error_ratio.toFixed(1)}x</strong> more absolute error at 50-60 minutes than 0-10 minutes.</p><p><strong>{(findings.top_one_percent_error_share * 100).toFixed(0)}%</strong> of 30-minute absolute error came from the worst 1% of intervals.</p><p><strong>{number.format(findings.actual_intervals_above_1000)}</strong> intervals cleared above $1,000/MWh; the maximum reached {money.format(findings.max_actual_price)}.</p></div></section>
      <section className="method"><span className="kicker">METHOD</span><h2>Vintage-aware by design</h2><p>Each observation preserves forecast run, availability time, target interval and realised VIC1 price. Forecasts dated after their target are rejected automatically. Event rankings use one declared lead time, avoiding double-counting multiple vintages of the same outcome.</p><div className="links"><a href="https://github.com/spgg224/vic-forecast-monitor">View methodology and code</a></div></section>
    </main>
    <footer>Built by Sparsh Basantani / Public AEMO data / Historical research</footer>
  </>;
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
