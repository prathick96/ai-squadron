import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type AgentRow,
  type ConfidenceReport,
  type ManualReviewItem,
  type PipelineRun,
  type PortfolioSlot,
  type RevenueSummary,
  type Venture,
} from "./api";

function formatUsd(n: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

function elapsed(iso: string): string {
  const secs = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ${secs % 60}s`;
  return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`;
}

const PRODUCT_STAGES = [
  "RESEARCH_NODE", "CEO_NODE", "PRODUCT_VP_NODE", "PRODUCT_MANAGER_NODE",
  "ENGINEERING_NODE", "QA_TECHNICAL_NODE", "LEGAL_NODE", "SECURITY_NODE",
  "ACCOUNT_DISTRIBUTION_NODE", "DEPLOYMENT_NODE", "MARKETING_SEO_NODE", "PRODUCT_GROWTH_NODE",
];

const MEDIA_STAGES = [
  "RESEARCH_NODE", "CEO_NODE", "MEDIA_VP_NODE", "SCRIPT_NODE", "VOICE_NODE",
  "VIDEO_NODE", "THUMBNAIL_NODE", "SEO_METADATA_NODE", "QA_COMPLIANCE_NODE",
  "LEGAL_NODE", "SECURITY_NODE", "ACCOUNT_DISTRIBUTION_NODE",
  "PUBLISHING_NODE", "ANALYTICS_NODE", "ANTI_BAN_NODE", "MEDIA_GROWTH_NODE",
];

function stageIndex(run: PipelineRun): number {
  const stages = run.department === "MEDIA" ? MEDIA_STAGES : PRODUCT_STAGES;
  const idx = stages.indexOf(run.current_stage);
  return idx >= 0 ? idx : 0;
}

function PipelineStatusBadge({ status }: { status: PipelineRun["status"] }) {
  const colors: Record<string, string> = {
    STARTED: "#888",
    RUNNING: "#4af",
    COMPLETED: "#4c4",
    FAILED: "#f44",
    MANUAL_REVIEW: "#fa4",
  };
  return (
    <span
      style={{
        background: colors[status] ?? "#888",
        color: "#000",
        borderRadius: 4,
        padding: "1px 6px",
        fontSize: "0.7rem",
        fontWeight: 700,
        fontFamily: "monospace",
      }}
    >
      {status}
    </span>
  );
}

function PipelineProgressBar({ run }: { run: PipelineRun }) {
  const stages = run.department === "MEDIA" ? MEDIA_STAGES : PRODUCT_STAGES;
  const idx = stageIndex(run);
  const pct = run.status === "COMPLETED" ? 100 : Math.round(((idx + 1) / stages.length) * 100);

  return (
    <div style={{ marginTop: 6 }}>
      <div style={{ fontSize: "0.72rem", color: "var(--muted)", marginBottom: 3 }}>
        {run.current_stage.replace(/_NODE$/, "").replace(/_/g, " ")} — {pct}%
      </div>
      <div style={{ background: "#222", borderRadius: 3, height: 6, overflow: "hidden" }}>
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: run.status === "FAILED" ? "#f44" :
                        run.status === "MANUAL_REVIEW" ? "#fa4" : "var(--accent)",
            transition: "width 0.4s ease",
          }}
        />
      </div>
    </div>
  );
}

function ConfirmKillDialog({
  venture,
  onConfirm,
  onCancel,
  loading,
  error,
}: {
  venture: Venture;
  onConfirm: () => void;
  onCancel: () => void;
  loading: boolean;
  error: string | null;
}) {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.75)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        style={{
          background: "#111",
          border: "1px solid #f44",
          borderRadius: 8,
          padding: "24px 28px",
          maxWidth: 420,
          width: "90%",
        }}
      >
        <h3 style={{ color: "#f44", marginTop: 0, fontFamily: "monospace" }}>Kill Venture?</h3>
        <p style={{ fontSize: "0.85rem", marginBottom: 6 }}>
          <strong className="mono">{venture.venture_id}</strong>
        </p>
        <p style={{ fontSize: "0.82rem", color: "var(--muted)", marginBottom: 16 }}>
          Niche: {venture.niche || "—"} · Status: {venture.status}
        </p>
        <p style={{ fontSize: "0.82rem", marginBottom: 20 }}>
          This will permanently mark the venture as <strong>KILLED</strong> and remove it from active
          operations. This cannot be undone.
        </p>
        {error && (
          <div
            style={{
              color: "#f66",
              fontSize: "0.8rem",
              marginBottom: 12,
              fontFamily: "monospace",
            }}
          >
            ⚠ {error}
          </div>
        )}
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button
            onClick={onCancel}
            disabled={loading}
            style={{
              background: "#222",
              color: "var(--fg)",
              border: "1px solid var(--border)",
              borderRadius: 4,
              padding: "6px 16px",
              cursor: "pointer",
              fontSize: "0.82rem",
            }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            style={{
              background: loading ? "#333" : "#f44",
              color: loading ? "var(--muted)" : "#fff",
              border: "none",
              borderRadius: 4,
              padding: "6px 16px",
              fontWeight: 700,
              cursor: loading ? "not-allowed" : "pointer",
              fontSize: "0.82rem",
              fontFamily: "monospace",
            }}
          >
            {loading ? "Killing…" : "Yes, Kill It"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ActiveRunCard({ run, onRefresh }: { run: PipelineRun; onRefresh: () => void }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const elapsedStr = elapsed(run.started_at);

  return (
    <div
      style={{
        border: "1px solid var(--border)",
        borderRadius: 6,
        padding: "10px 14px",
        marginBottom: 8,
        background: "#111",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span className="mono" style={{ fontSize: "0.78rem" }}>
          {run.venture_id}
        </span>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <span style={{ fontSize: "0.72rem", color: "var(--muted)" }}>{elapsedStr}</span>
          <PipelineStatusBadge status={run.status} />
          <span
            style={{
              fontSize: "0.72rem",
              background: "#1a2a1a",
              color: "var(--accent)",
              padding: "1px 5px",
              borderRadius: 3,
              fontFamily: "monospace",
            }}
          >
            {run.department}
          </span>
        </div>
      </div>

      <PipelineProgressBar run={run} />

      {run.last_error && (
        <div
          style={{
            marginTop: 6,
            fontSize: "0.72rem",
            color: "#f66",
            fontFamily: "monospace",
          }}
        >
          ⚠ {run.last_error.slice(0, 120)}
        </div>
      )}

      {run.recent_events.length > 0 && (
        <div style={{ marginTop: 6 }}>
          {run.recent_events.slice(-3).map((ev, i) => (
            <div
              key={i}
              style={{
                fontSize: "0.7rem",
                color: "var(--muted)",
                fontFamily: "monospace",
                lineHeight: 1.5,
              }}
            >
              › {String((ev as Record<string, unknown>).event_type ?? JSON.stringify(ev)).slice(0, 60)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
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

  // Venture management state
  const [ventures, setVentures] = useState<Venture[]>([]);
  const [killTarget, setKillTarget] = useState<Venture | null>(null);
  const [killing, setKilling] = useState(false);
  const [killError, setKillError] = useState<string | null>(null);

  const refreshVentures = useCallback(async () => {
    try {
      const res = await api.ventures();
      setVentures(res.ventures);
    } catch {
      /* silent */
    }
  }, []);

  const confirmKill = useCallback(async () => {
    if (!killTarget) return;
    setKilling(true);
    setKillError(null);
    try {
      await api.killVenture(killTarget.venture_id);
      setKillTarget(null);
      await refreshVentures();
    } catch (e) {
      setKillError(e instanceof Error ? e.message : "Kill failed");
    } finally {
      setKilling(false);
    }
  }, [killTarget, refreshVentures]);

  // Week 5 — pipeline control state
  const [pipelineDept, setPipelineDept] = useState<"PRODUCT" | "MEDIA" | "AUTO">("AUTO");
  const [launching, setLaunching] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [recentRuns, setRecentRuns] = useState<PipelineRun[]>([]);
  const pollTimers = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());

  const refreshRecentRuns = useCallback(async () => {
    try {
      const res = await api.pipelineRecent();
      setRecentRuns(res.runs);
    } catch {
      /* silent */
    }
  }, []);

  const pollRun = useCallback(
    (run_id: string) => {
      if (pollTimers.current.has(run_id)) return;
      const timer = setInterval(async () => {
        try {
          const run = await api.pipelineStatus(run_id);
          setRecentRuns((prev) =>
            prev.map((r) => (r.run_id === run_id ? run : r)),
          );
          if (run.status !== "STARTED" && run.status !== "RUNNING") {
            clearInterval(pollTimers.current.get(run_id));
            pollTimers.current.delete(run_id);
          }
        } catch {
          clearInterval(pollTimers.current.get(run_id));
          pollTimers.current.delete(run_id);
        }
      }, 3000);
      pollTimers.current.set(run_id, timer);
    },
    [],
  );

  const launchPipeline = useCallback(async () => {
    setLaunching(true);
    setLaunchError(null);
    try {
      const result = await api.pipelineRun(pipelineDept);
      const stub: PipelineRun = {
        run_id: result.run_id,
        venture_id: result.venture_id,
        department: pipelineDept,
        status: "STARTED",
        current_stage: "RESEARCH_NODE",
        started_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        completed_at: null,
        event_count: 0,
        recent_events: [],
        last_error: null,
      };
      setRecentRuns((prev) => [stub, ...prev]);
      pollRun(result.run_id);
    } catch (e) {
      setLaunchError(e instanceof Error ? e.message : "Launch failed");
    } finally {
      setLaunching(false);
    }
  }, [pipelineDept, pollRun]);

  // Restart polling for any RUNNING runs after page refresh
  useEffect(() => {
    recentRuns.forEach((r) => {
      if (r.status === "STARTED" || r.status === "RUNNING") {
        pollRun(r.run_id);
      }
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Cleanup timers on unmount
  useEffect(() => {
    return () => pollTimers.current.forEach((t) => clearInterval(t));
  }, []);

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
    refreshRecentRuns();
    refreshVentures();
    const id = setInterval(refresh, 8000);
    return () => clearInterval(id);
  }, [refresh, refreshRecentRuns, refreshVentures]);

  useEffect(() => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    // window.location.host includes port when non-standard (e.g. localhost:5173 in dev).
    // In production (Railway HTTPS/443) it's just the hostname — no :PORT needed.
    const ws = new WebSocket(`${proto}//${window.location.host}/api/ws/live`);
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "tick" && msg.revenue) setRevenue(msg.revenue);
        // Update active runs from WebSocket tick
        if (msg.active_pipeline_runs) {
          const active: PipelineRun[] = msg.active_pipeline_runs;
          setRecentRuns((prev) =>
            prev.map((r) => {
              const live = active.find((a) => a.run_id === r.run_id);
              return live ? { ...r, ...live } : r;
            }),
          );
        }
      } catch {
        /* ignore */
      }
    };
    return () => ws.close();
  }, []);

  const mrr = revenue?.mrr_usd ?? 0;
  const burn = revenue?.burn_usd ?? 0;
  const net = revenue?.net_mrr_usd ?? 0;

  const activeVentures = ventures.filter((v) => v.status !== "KILLED");
  const statusOrder: Record<string, number> = { FAILED: 0, DEVELOPMENT: 1, QA: 2, IDEATION: 3, LIVE: 4, SCALING: 5 };
  const sortedVentures = [...activeVentures].sort(
    (a, b) => (statusOrder[a.status] ?? 9) - (statusOrder[b.status] ?? 9),
  );

  return (
    <div className="app">
      {killTarget && (
        <ConfirmKillDialog
          venture={killTarget}
          onConfirm={confirmKill}
          onCancel={() => { setKillTarget(null); setKillError(null); }}
          loading={killing}
          error={killError}
        />
      )}
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
            {confidence.leading_indicators?.ventures_with_revenue ?? 0} · Active dev{" "}
            {confidence.leading_indicators?.live_venture_count ?? 0} · Runs{" "}
            {confidence.leading_indicators?.completed_pipeline_runs ?? 0} · Reviews pending{" "}
            {confidence.leading_indicators?.manual_review_pending ?? 0}
          </div>
        </section>
      )}

      {/* Week 5 — Pipeline Control Panel */}
      <section className="panel" style={{ marginTop: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2>Pipeline Control</h2>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <select
              value={pipelineDept}
              onChange={(e) => setPipelineDept(e.target.value as typeof pipelineDept)}
              style={{
                background: "#111",
                color: "var(--fg)",
                border: "1px solid var(--border)",
                borderRadius: 4,
                padding: "4px 8px",
                fontSize: "0.8rem",
              }}
            >
              <option value="AUTO">AUTO (CEO decides)</option>
              <option value="PRODUCT">PRODUCT (SaaS)</option>
              <option value="MEDIA">MEDIA (Content channel)</option>
            </select>
            <button
              onClick={launchPipeline}
              disabled={launching}
              style={{
                background: launching ? "#333" : "var(--accent)",
                color: launching ? "var(--muted)" : "#000",
                border: "none",
                borderRadius: 4,
                padding: "6px 16px",
                fontSize: "0.82rem",
                fontWeight: 700,
                cursor: launching ? "not-allowed" : "pointer",
                fontFamily: "monospace",
              }}
            >
              {launching ? "Launching…" : "Launch New Venture"}
            </button>
          </div>
        </div>

        {launchError && (
          <div style={{ color: "#f66", fontSize: "0.78rem", marginTop: 6 }}>
            ⚠ {launchError}
          </div>
        )}

        {(() => {
          const killedIds = new Set(ventures.filter((v) => v.status === "KILLED").map((v) => v.venture_id));
          const visibleRuns = recentRuns.filter((r) => !killedIds.has(r.venture_id));
          return visibleRuns.length === 0 ? (
            <p style={{ color: "var(--muted)", fontSize: "0.82rem", marginTop: 8 }}>
              No pipeline runs yet. Click "Launch New Venture" to start.
            </p>
          ) : (
            <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: "0.72rem", color: "var(--muted)", marginBottom: 6 }}>
                {visibleRuns.length} run{visibleRuns.length !== 1 ? "s" : ""} total —{" "}
                {visibleRuns.filter((r) => r.status === "RUNNING" || r.status === "STARTED").length} active
              </div>
              {visibleRuns.map((run) => (
                <ActiveRunCard key={run.run_id} run={run} onRefresh={refreshRecentRuns} />
              ))}
            </div>
          );
        })()}
      </section>

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
              <p style={{ fontSize: "0.75rem", color: "var(--muted)", marginBottom: "0.5rem" }}>
                Fix the root cause, then launch a new venture. Use Dismiss to clear stale items.
              </p>
              {reviews.map((r) => (
                <div
                  key={r.id ?? r.venture_id + (r.created_at ?? "")}
                  style={{
                    border: "1px solid #f84",
                    borderRadius: 6,
                    padding: "0.6rem 0.75rem",
                    marginBottom: "0.5rem",
                    background: "#1a1200",
                  }}
                >
                  <div style={{ fontSize: "0.78rem", fontFamily: "monospace", color: "#f84" }}>
                    {r.artifact_type ?? "BUILD"} · {r.venture_id}
                  </div>
                  <div style={{ fontSize: "0.75rem", marginTop: 3, color: "#ddd" }}>
                    {r.review_reason}
                  </div>
                  <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                    {(["APPROVED", "REJECTED", "DEFERRED"] as const).map((action) => (
                      <button
                        key={action}
                        style={{
                          fontSize: "0.68rem",
                          padding: "2px 8px",
                          borderRadius: 4,
                          border: "1px solid #444",
                          background: action === "APPROVED" ? "#1a3a1a" : action === "REJECTED" ? "#3a1a1a" : "#222",
                          color: action === "APPROVED" ? "#4c4" : action === "REJECTED" ? "#f44" : "#aaa",
                          cursor: "pointer",
                          fontFamily: "monospace",
                        }}
                        onClick={() => {
                          if (!r.id) return;
                          api.resolveReview(r.id, action)
                            .then(() => refresh())
                            .catch((e) => console.error("resolve failed", e));
                        }}
                      >
                        {action === "APPROVED" ? "✓ Approve" : action === "REJECTED" ? "✗ Reject" : "— Dismiss"}
                      </button>
                    ))}
                  </div>
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

      {/* Venture Management — Kill Switch */}
      <section className="panel" style={{ marginTop: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2>Venture Management</h2>
          <span style={{ fontSize: "0.72rem", color: "var(--muted)" }}>
            {activeVentures.length} active · click Kill to shut down failed ventures
          </span>
        </div>

        {sortedVentures.length === 0 ? (
          <p style={{ color: "var(--muted)", fontSize: "0.82rem", marginTop: 8 }}>
            No active ventures found.
          </p>
        ) : (
          <table className="agent-table" style={{ marginTop: 10 }}>
            <thead>
              <tr>
                <th>Venture ID</th>
                <th>Niche</th>
                <th>Type</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {sortedVentures.map((v) => {
                const isRevenue = v.status === "LIVE" || v.status === "SCALING";
                return (
                  <tr key={v.venture_id}>
                    <td className="mono" style={{ fontSize: "0.75rem" }}>{v.venture_id}</td>
                    <td style={{ fontSize: "0.78rem" }}>{v.niche || "—"}</td>
                    <td className="mono" style={{ fontSize: "0.72rem", color: "var(--muted)" }}>
                      {v.venture_type?.replace(/_/g, " ") ?? "—"}
                    </td>
                    <td>
                      <span
                        style={{
                          background:
                            v.status === "LIVE" || v.status === "SCALING" ? "#1a4a1a" :
                            v.status === "DEVELOPMENT" || v.status === "QA" ? "#1a2a3a" :
                            "#2a1a1a",
                          color:
                            v.status === "LIVE" || v.status === "SCALING" ? "#4c4" :
                            v.status === "DEVELOPMENT" || v.status === "QA" ? "#4af" :
                            "#f66",
                          borderRadius: 4,
                          padding: "1px 6px",
                          fontSize: "0.7rem",
                          fontWeight: 700,
                          fontFamily: "monospace",
                        }}
                      >
                        {v.status}
                      </span>
                    </td>
                    <td>
                      {isRevenue ? (
                        <span
                          title="Generating revenue — cannot kill"
                          style={{
                            fontSize: "0.72rem",
                            color: "#4c4",
                            fontFamily: "monospace",
                          }}
                        >
                          Protected
                        </span>
                      ) : (
                        <button
                          onClick={() => { setKillTarget(v); setKillError(null); }}
                          style={{
                            background: "#2a0a0a",
                            color: "#f66",
                            border: "1px solid #f44",
                            borderRadius: 4,
                            padding: "2px 10px",
                            fontSize: "0.72rem",
                            fontWeight: 700,
                            cursor: "pointer",
                            fontFamily: "monospace",
                          }}
                        >
                          Kill
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

    </div>
  );
}
