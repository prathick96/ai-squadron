const API_BASE = import.meta.env.VITE_API_URL ?? "";

export type AgentRow = {
  agent_name: string;
  status: string;
  current_task: string;
  tokens_used: number;
  latency_ms: number;
  retry_count: number;
  success_ratio: number;
  updated_at: string;
};

export type RevenueSummary = {
  mrr_usd: number;
  arr_usd: number;
  burn_usd: number;
  net_mrr_usd: number;
  burn_earn_ratio: number;
  by_source: Record<string, number>;
  updated_at: string;
};

export type PortfolioSlot = {
  slot: number;
  venture_id: string | null;
  status: string;
  niche: string;
  mrr_usd: number;
};

export type ConfidenceReport = {
  confidence_score: number;
  confidence_tier: string;
  mrr_current_usd: number;
  burn_current_usd: number;
  burn_earn_ratio: number;
  forecast_p10_mrr_12mo: number;
  forecast_p50_mrr_12mo: number;
  forecast_p90_mrr_12mo: number;
  leading_indicators: Record<string, number>;
  recommended_actions: string[];
  scale_ventures: string[];
  kill_ventures: string[];
};

export type ManualReviewItem = {
  id?: string;
  venture_id: string;
  run_id: string;
  review_reason: string;
  artifact_type?: string;
  status: string;
  priority?: string;
  created_at?: string;
};

export type PipelineRunStatus =
  | "STARTED"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "MANUAL_REVIEW";

export type PipelineRun = {
  run_id: string;
  venture_id: string;
  department: "PRODUCT" | "MEDIA" | "AUTO";
  status: PipelineRunStatus;
  current_stage: string;
  started_at: string;
  updated_at: string;
  completed_at: string | null;
  event_count: number;
  recent_events: Record<string, unknown>[];
  last_error: string | null;
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  agents: () => get<{ agents: AgentRow[]; source: string }>("/api/agents"),
  revenue: () => get<RevenueSummary>("/api/revenue"),
  revenuePlan: () =>
    get<{ headline: string; actions: string[]; kill_candidates: string[]; scale_candidates: string[] }>(
      "/api/revenue/plan",
    ),
  portfolio: () =>
    get<{ total_slots: number; live_count: number; slots: PortfolioSlot[] }>("/api/portfolio"),
  trends: () =>
    get<{
      trends: { topic: string; score: number; region: string; covered: boolean }[];
      coverage_pct: number;
      updated_at: string;
    }>("/api/trends"),
  security: () =>
    get<{ alerts: { severity: string; platform: string; message: string; at: string }[] }>(
      "/api/security/alerts",
    ),
  confidence: () => get<ConfidenceReport>("/api/confidence"),
  scorecards: () =>
    get<{ scorecards: Record<string, unknown>[]; count: number }>("/api/scorecards"),
  manualReview: () =>
    get<{ items: ManualReviewItem[]; count: number }>("/api/manual-review"),
  runRevenueCycle: () => post<unknown>("/api/revenue/run-cycle", {}),

  // Week 5 — pipeline control
  pipelineRun: (department: "PRODUCT" | "MEDIA" | "AUTO" = "AUTO", venture_id?: string) =>
    post<{ run_id: string; venture_id: string; status: string }>("/api/pipeline/run", {
      department,
      venture_id: venture_id ?? null,
    }),
  pipelineStatus: (run_id: string) => get<PipelineRun>(`/api/pipeline/${run_id}`),
  pipelineRecent: () =>
    get<{ runs: PipelineRun[]; count: number }>("/api/pipeline/recent"),
};
