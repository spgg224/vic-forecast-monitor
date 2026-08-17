import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import "./extras.css";
import "./decision.css";

type Horizon = { horizon_minutes: string; observations: number; mae: number; rmse: number; median_absolute_error: number; bias: number; p95_absolute_error: number };
type Scorecard = { coverage: { start: string; end: string; forecast_vintages: number; target_intervals: number }; overall: Horizon; by_horizon: Horizon[] };
type Vintage = { issue_time: string; horizon_minutes: number; forecast_price: number };
type Event = { issue_time: string; target_time: string; horizon_minutes: number; forecast_price: number; actual_price: number; forecast_error: number; absolute_error: number; vintages: Vintage[] };
type Events = { lead_minutes: number; events: Event[] };
type Findings = { far_to_near_error_ratio: number; top_one_percent_error_share: number; actual_intervals_above_1000: number; max_actual_price: number; thirty_minute_demand_mae_mw: number; absolute_demand_price_error_correlation: number; thirty_minute_net_interchange_mae_mw: number; absolute_interchange_price_error_correlation: number };
type ModelSummary = { model: string; training_start: string; training_end: string; test_start: string; test_end: string; training_intervals: number; test_intervals: number; aemo_mae: number; model_mae: number; mae_improvement_percent: number; warning: string };
type ModelSignal = { target_time: string; issue_time: string; forecast_price: number; model_fair_value: number; actual_price: number | null; model_edge: number; signal: string };
type LiveData = { generated_at: string; source: string; refresh_note: string; rows: ModelSignal[] };

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

function LiveChart({ rows }: { rows: ModelSignal[] }) {
  const values = rows.flatMap(row => [row.forecast_price, row.model_fair_value, row.actual_price].filter((value): value is number => value !== null));
  const low = Math.min(...values), high = Math.max(...values), span = Math.max(1, high - low);
  const point = (value: number, index: number) => `${5 + index * 90 / Math.max(1, rows.length - 1)},${92 - (value - low) / span * 82}`;
  const forecast = rows.map((row, index) => point(row.forecast_price, index)).join(" ");
  const model = rows.map((row, index) => point(row.model_fair_value, index)).join(" ");
  const actualRows = rows.map((row, index) => ({ ...row, index })).filter(row => row.actual_price !== null);
  const actual = actualRows.map(row => point(row.actual_price!, row.index)).join(" ");
  return <div className="liveChart"><svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Rolling AEMO forecast, model fair value and actual VIC price"><polyline points={forecast} className="aemoSeries"/><polyline points={model} className="modelSeries"/><polyline points={actual} className="actualSeries"/></svg><div className="liveLegend"><span><i className="aemoDot"/>AEMO forecast</span><span><i className="modelDot"/>Model fair value</span><span><i className="actualDot"/>Actual RRP</span></div><div className="chartAxis"><span>{new Date(rows[0].target_time).toLocaleTimeString("en-AU", {hour:"2-digit",minute:"2-digit"})}</span><span>Dispatch interval</span><span>{new Date(rows.at(-1)!.target_time).toLocaleTimeString("en-AU", {hour:"2-digit",minute:"2-digit"})}</span></div></div>;
}

function App() {
  const [scores, setScores] = useState<Scorecard | null>(null);
  const [events, setEvents] = useState<Events | null>(null);
  const [findings, setFindings] = useState<Findings | null>(null);
  const [selected, setSelected] = useState<Event | null>(null);
  const [modelSummary, setModelSummary] = useState<ModelSummary | null>(null);
  const [selectedSignal, setSelectedSignal] = useState<ModelSignal | null>(null);
  const [live, setLive] = useState<LiveData | null>(null);
  useEffect(() => {
    Promise.all(["scorecard", "events", "findings", "model_summary", "live"].map(name => fetch(`${import.meta.env.BASE_URL}data/${name}.json`).then(r => r.json())))
      .then(([scoreData, eventData, findingData, modelData, liveData]) => { setScores(scoreData); setEvents(eventData); setFindings(findingData); setModelSummary(modelData); setLive(liveData); setSelectedSignal(liveData.rows.at(-1)); setSelected(eventData.events[0]); });
  }, []);
  const dates = useMemo(() => scores ? `${new Date(scores.coverage.start).toLocaleDateString("en-AU")} - ${new Date(scores.coverage.end).toLocaleDateString("en-AU")}` : "Loading", [scores]);
  if (!scores || !events || !findings || !modelSummary || !selectedSignal || !live) return <main className="loading">Loading VIC forecast data...</main>;
  const near = scores.by_horizon[0], far = scores.by_horizon.at(-1)!;
  return <>
    <header><div className="eyebrow">AEMO PUBLIC DATA / HISTORICAL ANALYSIS</div><h1>VIC Forecast Monitor</h1><p>When five-minute electricity price forecasts diverged from market reality.</p><div className="meta"><span>VIC1</span><span>{dates}</span><span>Not a live trading signal</span></div></header>
    <main>
      <section className="decision">
        <div className="decisionIntro"><span className="liveBadge">LIVE AEMO FEED</span><h2>Thirty minutes before dispatch, does our estimate disagree with AEMO?</h2><p>The model estimates the eventual VIC1 spot price using only information available at the forecast time. A large difference is a research signal to investigate—not an executable market price.</p></div>
        <div className="signalPicker"><label htmlFor="signal">Rolling interval</label><select id="signal" value={selectedSignal.target_time} onChange={e => setSelectedSignal(live.rows.find(row => row.target_time === e.target.value) ?? selectedSignal)}>{live.rows.map(row => <option value={row.target_time} key={row.target_time}>{new Date(row.target_time).toLocaleString("en-AU", {dateStyle:"medium",timeStyle:"short"})} / {row.signal}</option>)}</select><small>Updated {new Date(live.generated_at).toLocaleString("en-AU")}</small></div>
        <div className="priceComparison"><article><span>AEMO 30-min forecast</span><strong>{money.format(selectedSignal.forecast_price)}</strong><small>Public market forecast</small></article><article className="modelValue"><span>Model fair value</span><strong>{money.format(selectedSignal.model_fair_value)}</strong><small>Estimated realised RRP</small></article><article><span>Actual outcome</span><strong>{selectedSignal.actual_price === null ? "Awaiting dispatch" : money.format(selectedSignal.actual_price)}</strong><small>{selectedSignal.actual_price === null ? "Not known yet" : "Realised VIC1 RRP"}</small></article></div>
        <div className={`signalCall ${selectedSignal.model_edge >= 0 ? "higher" : "lower"}`}><span>FORECAST-DISAGREEMENT SIGNAL</span><strong>{selectedSignal.signal}</strong><p>Model is {money.format(Math.abs(selectedSignal.model_edge))} {selectedSignal.model_edge >= 0 ? "above" : "below"} AEMO.</p></div>
        <div className="livePlot"><div><span className="kicker">ROLLING MARKET VIEW</span><h3>Forecasts versus realised VIC price</h3><p>The actual line stops where dispatch outcomes are not yet available.</p></div><LiveChart rows={live.rows}/></div>
      </section>
      <section className="explain"><span className="kicker">HOW TO READ THIS</span><div><p><b>1</b><strong>AEMO forecast</strong><span>What the public five-minute pre-dispatch run expected.</span></p><p><b>2</b><strong>Model fair value</strong><span>Our independent estimate using demand, renewables, interchange, revisions and known prior prices.</span></p><p><b>3</b><strong>Actual outcome</strong><span>Used afterward to score both forecasts on untouched test data.</span></p></div></section>
      <section className="modelScore"><div><span className="kicker">OUT-OF-SAMPLE SCORECARD</span><h2>The model improved normal price estimation, but this is not yet trading P&amp;L.</h2><p>Trained Jan-Sep 2025. Tested Oct-Dec 2025. No test outcomes were used to fit the model.</p></div><div className="scoreCompare"><p><span>AEMO MAE</span><strong>{money.format(modelSummary.aemo_mae)}</strong></p><p><span>Model MAE</span><strong>{money.format(modelSummary.model_mae)}</strong></p><p className="improve"><span>Improvement</span><strong>{modelSummary.mae_improvement_percent.toFixed(1)}%</strong></p></div></section>
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
      <section className="findings"><span className="kicker">FULL-YEAR FINDINGS</span><div><p><strong>{findings.far_to_near_error_ratio.toFixed(1)}x</strong> more absolute error at 50-60 minutes than 0-10 minutes.</p><p><strong>{(findings.top_one_percent_error_share * 100).toFixed(0)}%</strong> of 30-minute absolute error came from the worst 1% of intervals.</p><p><strong>{findings.thirty_minute_demand_mae_mw.toFixed(1)} MW</strong> demand MAE, but only {findings.absolute_demand_price_error_correlation.toFixed(3)} correlation with absolute price error.</p><p><strong>{findings.thirty_minute_net_interchange_mae_mw.toFixed(1)} MW</strong> net-interchange MAE, with only {findings.absolute_interchange_price_error_correlation.toFixed(3)} correlation with absolute price error.</p></div></section>
      <section className="method"><span className="kicker">METHOD</span><h2>Vintage-aware by design</h2><p>Each observation preserves forecast run, availability time, target interval and realised VIC1 price. Forecasts dated after their target are rejected automatically. Event rankings use one declared lead time, avoiding double-counting multiple vintages of the same outcome.</p><div className="links"><a href="https://github.com/spgg224/vic-forecast-monitor">View methodology and code</a></div></section>
    </main>
    <footer>Built by Sparsh Basantani / Public AEMO data / Historical research</footer>
  </>;
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
