export interface DashboardUser {
  uid: string;
  email: string | null;
  name: string | null;
  picture: string | null;
}

export interface MetricCard {
  label: string;
  value: string | number;
  helper: string | null;
  tone: string;
}

export interface OverviewResponse {
  user: DashboardUser;
  generated_at: string;
  cards: MetricCard[];
  ux_metrics: {
    unconfirmed_draft_rate: number;
    correction_rate: number;
    fallback_rate: number;
    messages_per_confirmed_log: number;
    media_processing_events: number;
    average_session_hours: number;
    draft_logs: number;
    confirmed_logs: number;
    [key: string]: number | string | null;
  };
  recent_escalations: Array<{
    id: string;
    report_text: string;
    status: string;
    platform: string | null;
    created_at: string;
    organization_name: string | null;
    user_name: string | null;
  }>;
  document_breakdown: Array<{
    label: string;
    value: number;
  }>;
  session_breakdown: Array<{
    label: string;
    value: number;
  }>;
}

export interface OrganizationDashboardRow {
  id: string;
  name: string;
  created_at: string | null;
  member_count: number;
  document_count: number;
  work_log_count: number;
  conversation_count: number;
  active_session_count: number;
}

export interface OrganizationsResponse {
  organizations: OrganizationDashboardRow[];
}

export interface DocumentDashboardRow {
  id: string;
  org_id: string;
  organization_name: string | null;
  owner_user_id: string | null;
  owner_name: string | null;
  display_name: string;
  filename: string;
  document_kind: string;
  content_type: string | null;
  source_type: string;
  status: string;
  size_bytes: number | null;
  summary: string | null;
  tags: string[];
  update_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface DocumentsDashboardResponse {
  documents: DocumentDashboardRow[];
}

export interface EscalationDashboardRow {
  id: string;
  conversation_id: string | null;
  org_id: string | null;
  organization_name: string | null;
  user_id: string | null;
  user_name: string | null;
  platform: string | null;
  report_text: string;
  status: string;
  destination: string | null;
  error_text: string | null;
  turn_count: number;
  work_log_count: number;
  created_at: string | null;
  sent_at: string | null;
}

export interface EscalationsResponse {
  escalations: EscalationDashboardRow[];
}

export interface ConversationTurn {
  direction: string;
  platform: string | null;
  message_type: string;
  body_text: string;
  occurred_at: string;
  created_at: string;
  metadata: Record<string, any>;
}

export interface ConversationLogRow {
  conversation_id: string;
  org_id: string | null;
  organization_name: string | null;
  user_id: string | null;
  user_name: string | null;
  platform: string | null;
  status: string | null;
  started_at: string | null;
  last_message_at: string | null;
  turn_count: number;
  work_log_count: number;
  escalation_count: number;
  turns: ConversationTurn[];
}

export interface LogsResponse {
  conversations: ConversationLogRow[];
}

export interface TokenUsageTotals {
  request_count: number;
  success_count: number;
  error_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  average_total_tokens: number;
  last_event_at: string | null;
  estimated: boolean;
}

export interface TokenUsageBreakdownRow {
  provider: string;
  model: string;
  purpose: string | null;
  request_count: number;
  success_count: number;
  error_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  average_total_tokens: number;
  first_seen_at: string | null;
  last_seen_at: string | null;
  estimated: boolean;
}

export interface TokenUsageDailyRow {
  date: string;
  request_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  error_count: number;
  estimated: boolean;
}

export interface TokenUsageRecentRow {
  id: string;
  conversation_id: string | null;
  provider: string;
  model: string;
  purpose: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  status: string;
  created_at: string | null;
  estimated: boolean;
}

export interface TokenUsageResponse {
  generated_at: string;
  window_days: number;
  note: string;
  totals: TokenUsageTotals;
  by_model: TokenUsageBreakdownRow[];
  by_purpose: TokenUsageBreakdownRow[];
  daily: TokenUsageDailyRow[];
  recent: TokenUsageRecentRow[];
}
