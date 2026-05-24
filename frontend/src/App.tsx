import { useCallback, useEffect, useState } from "react";
import {
  api,
  type AgentRow,
  type ConfidenceReport,
  type ManualReviewItem,
  type PortfolioSlot,
  type RevenueSummary,
} from "./api";

function formatUsd(n: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

export default function App() {
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [revenue, setRevenue] = useState<RevenueSummary | null>(null);
  const [slots, setSlots] = useState<PortfolioSlot[]>([]);
  const [trends, setTrends] = useState<
    { topic: string; score: number; region: string; covered: boolean }[]
  >([]);
  const [coveragePct, setCoveragePct] = useState(0);
  const [alerts, setAlerts] = useState<
    { severity: string; platform: string; message: string }[]
  >([]);
  const [plan, setPlan] = useState<{ headline: string; actions: string[] } | null>(null);
  const [confidence, setConfidence] = useState<ConfidenceReport | null>(null);
  const [reviews, setReviews] = useState<ManualReviewItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dataSource, setDataSource] = useState("mock");
  const [lastTick, setLastTick] = useState<string>("");

  const refresh = useCallback(async () => {
    try {
      const [a, r, p, t, s, pl, conf, rev] = await Promise.all([
        api.agents(),
        api.revenue(),
        api.portfolio(),
        api.trends(),
        api.security(),
        api.revenuePlan(),
        api.confidence(),
        api.manualReview(),
      ]);
      setAgents(a.agents);
      setDataSource(a.source);
      setRevenue(r);
      setSlots(p.slots);
      setTrends(t.trends);
      setCoveragePct(t.coverage_pct);
      setAlerts(s.alerts);
      setPlan(pl);
      setConfidence(conf);
      setReviews(rev.items);
      setError(null);
      setLastTick(new Date().toLocaleTimeString());
    } catch (e) {
      setError(
        "API unreachable. Start: uvicorn apps.api.main:app --reload --port 8000",
      );
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 8000);
    return () => clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.hostname;
    const ws = new WebSocket(`${proto}//${host}:8000/api/ws/live`);
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "tick" && msg.revenue) setRevenue(msg.revenue);
      } catch {
        /* ignore */
      }
    };
    return () => ws.close();
  }, []);

  const mrr = revenue?.mrr_usd ?? 0;
  const burn = revenue?.burn_usd ?? 0;
  const net = revenue?.net_mrr_usd ?? 0;

  return (
    <div className="app">
      <header>
        <div>
          <h1>AI Squadron Command Center</h1>
          <p>Autonomous venture & media orchestration</p>
        </div>
        <div className="live-dot mono">
          LIVE · {lastTick || "—"} · {dataSource}
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <section className="ticker mono">
        <div className="stat">
          <div className="label">MRR</div>
          <div className={`value ${mrr > 0 ? "positive" : ""}`}>{formatUsd(mrr)}</div>
        </div>
        <div className="stat">
          <div className="label">ARR</div>
          <div className="value">{formatUsd(revenue?.arr_usd ?? mrr * 12)}</div>
        </div>
        <div className="stat">
          <div className="label">Burn (API + infra)</div>
          <div className="value negative">{formatUsd(burn)}</div>
        </div>
        <div className="stat">
          <div className="label">Net MRR</div>
          <div className={`value ${net >= 0 ? "positive" : "negative"}`}>
            {formatUsd(net)}
          </div>
        </div>
      </section>

      {confidence && (
        <section className="confidence-panel mono">
          <div className="conf-score">
            <span className="label">Confidence</span>
            <span className={`conf-value tier-${confidence.confidence_tier}`}>
              {confidence.confidence_score}/100
            </span>
            <span className="conf-tier">{confidence.confidence_tier}</span>
          </div>
          <div className="conf-forecast">
            <span>12mo MRR p10 {formatUsd(confidence.forecast_p10_mrr_12mo)}</span>
            <span> p50 {formatUsd(confidence.forecast_p50_mrr_12mo)}</span>
            <span> p90 {formatUsd(confidence.forecast_p90_mrr_12mo)}</span>
          </div>
          <div className="conf-indicators">
            QA {confidence.leading_indicators?.qa_first_pass_rate_pct ?? 0}% · Revenue ventures{" "}
            {confidence.leading_indicators?.ventures_with_revenue ?? 0} · Reviews pending{" "}
            {confidence.leading_indicators?.manual_review_pending ?? 0}
          </div>
        </section>
      )}

      <div className="grid grid-top">
        <section className="panel">
          <h2>Agent health & performance</h2>
          <table className="agent-table">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Status</th>
                <th>Task</th>
                <th>Tokens</th>
                <th>Success</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((a) => (
                <tr key={a.agent_name}>
                  <td className="mono">{a.agent_name.replace(/_/g, " ")}</td>
                  <td>
                    <span className={`badge ${a.status}`}>{a.status}</span>
                  </td>
                  <td>{a.current_task}</td>
                  <td className="mono">{a.tokens_used.toLocaleString()}</td>
                  <td className="mono">{(a.success_ratio * 100).toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="panel">
          <h2>Global trends vs portfolio ({coveragePct}% covered)</h2>
          {trends.map((t) => (
            <div key={t.topic} className="trend-row">
              <span style={{ width: 140 }}>{t.topic}</span>
              <div className="trend-bar">
                <div
                  className="trend-bar-inner"
                  style={{ width: `${t.score}%`, opacity: t.covered ? 1 : 0.45 }}
                />
              </div>
              <span className="mono" style={{ width: 36 }}>
                {t.score}
              </span>
              <span style={{ color: t.covered ? "var(--accent)" : "var(--muted)", width: 56 }}>
                {t.covered ? "covered" : "gap"}
              </span>
              <span className="mono" style={{ color: "var(--muted)" }}>
                {t.region}
              </span>
            </div>
          ))}
        </section>

        <section className="panel">
          <h2>Revenue orchestrator plan</h2>
          {plan && (
            <>
              <p style={{ fontSize: "0.85rem", marginBottom: "0.75rem" }}>{plan.headline}</p>
              <ul className="plan-list">
                {plan.actions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </>
          )}
          {reviews.length > 0 && (
            <>
              <h2 style={{ marginTop: "1rem" }}>Manual review queue</h2>
              {reviews.map((r) => (
                <div key={r.venture_id + (r.created_at ?? "")} className="alert" style={{ borderColor: "var(--warn)" }}>
                  <strong>{r.venture_id}</strong> — {r.review_reason}
                </div>
              ))}
            </>
          )}
          <h2 style={{ marginTop: "1rem" }}>Risk & security</h2>
          {alerts.map((al, i) => (
            <div key={i} className="alert">
              <strong>{al.platform}</strong> — {al.message}
            </div>
          ))}
        </section>
      </div>

      <section className="panel" style={{ marginTop: "1rem" }}>
        <h2>Portfolio progress (450 slots)</h2>
        <div className="portfolio-grid">
          {slots.map((s) => (
            <div
              key={s.slot}
              className={`portfolio-cell ${s.status}`}
              title={s.niche || s.status}
            />
          ))}
        </div>
        <div className="legend">
          <span className="IDEATION">Ideation</span>
          <span className="DEVELOPMENT">Development</span>
          <span className="LIVE">Live</span>
        </div>
      </section>
    </div>
  );
}
