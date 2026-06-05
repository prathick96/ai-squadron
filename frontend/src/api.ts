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

export type LedgerEntry = {
  venture_id: string;
  period_start: string;
  period_end: string;
  revenue_source: "STRIPE" | "ADSENSE" | "MANUAL";
  amount_usd: number;
  burn_usd: number;
  notes: string;
  created_at?: string;
};

export type LedgerEntryBody = Omit<LedgerEntry, "created_at">;

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

export type Venture = {
  venture_id: string;
  venture_type: string;
  niche: string;
  status: string;
  go_decision?: boolean;
  feasibility_score?: number | null;
  updated_at?: string;
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
  department: "PRODUCT";
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
  resolveReview: (review_id: string, status: "APPROVED" | "REJECTED" | "DEFERRED", notes?: string) =>
    fetch(`${API_BASE}/api/manual-review/${encodeURIComponent(review_id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, notes: notes ?? "" }),
    }).then(async (res) => {
      if (!res.ok) throw new Error(`resolve failed: ${res.status}`);
      return res.json() as Promise<{ ok: boolean; review_id: string; status: string }>;
    }),
  runRevenueCycle: () => post<unknown>("/api/revenue/run-cycle", {}),

  // Week 8 — ledger read/write
  ledger: (venture_id?: string) =>
    get<{ entries: LedgerEntry[]; count: number }>(
      venture_id ? `/api/revenue/ledger?venture_id=${encodeURIComponent(venture_id)}` : "/api/revenue/ledger",
    ),
  addLedgerEntry: (body: LedgerEntryBody) =>
    post<{ ok: boolean; entry: LedgerEntry }>("/api/revenue/ledger", body),

  // Venture management
  ventures: () => get<{ ventures: Venture[]; count: number }>("/api/ventures"),
  killVenture: (venture_id: string) =>
    fetch(`${API_BASE}/api/ventures/${encodeURIComponent(venture_id)}`, { method: "DELETE" }).then(
      async (res) => {
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error((data as { detail?: string }).detail ?? `${res.status}`);
        }
        return res.json() as Promise<{ ok: boolean; venture_id: string; status: string }>;
      },
    ),

  // Public storefront
  products: () =>
    get<{ products: { venture_id: string; niche: string; status: string; venture_type: string }[]; count: number }>(
      '/api/products',
    ),

  // Week 10 — build inspection
  buildFiles: (venture_id: string) =>
    get<{
      venture_id: string; build_dir: string; file_count: number;
      total_kb: number; dist_exists: boolean; dist_kb: number;
      validate: Record<string, string>; files: { path: string; size_bytes: number; preview: string }[];
    }>(`/api/builds/${encodeURIComponent(venture_id)}`),
  buildFile: (venture_id: string, path: string) =>
    get<{ venture_id: string; path: string; size_bytes: number; content: string }>(
      `/api/builds/${encodeURIComponent(venture_id)}/file?path=${encodeURIComponent(path)}`
    ),

  // Pipeline control
  pipelineRun: (venture_id?: string) =>
    post<{ run_id: string; venture_id: string; status: string }>("/api/pipeline/run", {
      department: "PRODUCT",
      venture_id: venture_id ?? null,
    }),
  pipelineStatus: (run_id: string) => get<PipelineRun>(`/api/pipeline/${run_id}`),
  pipelineRecent: () =>
    get<{ runs: PipelineRun[]; count: number }>("/api/pipeline/recent"),

  // Manual review override — proceed anyway (deploy directly, skip stuck gate)
  proceedPipeline: (run_id: string) =>
    post<{ ok: boolean; url: string; venture_id: string }>(
      `/api/pipeline/${encodeURIComponent(run_id)}/proceed`, {}
    ),

  // Deploy a specific venture to Railway
  deployVenture: (venture_id: string) =>
    post<{ ok: boolean; url: string; venture_id: string }>(
      `/api/ventures/${encodeURIComponent(venture_id)}/deploy`, {}
    ),
};
