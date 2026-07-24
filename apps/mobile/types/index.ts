export interface SessionInfo {
  session_id: string;
  created_at: string;
  model: string;
  title?: string;
}

export interface MetricItem {
  label: string;
  value: string;
  status: "good" | "neutral" | "warning";
}
