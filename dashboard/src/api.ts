import { isFirebaseConfigured } from './firebase';
import type {
  DashboardUser,
  OverviewResponse,
  OrganizationsResponse,
  DocumentsDashboardResponse,
  EscalationsResponse,
  LogsResponse,
  TokenUsageResponse,
  SessionSearchResponse,
  AdminAccessResponse,
  AdminUsersResponse,
  AddMemberPayload,
  AddMemberResponse,
  LinkEmailPayload,
  LinkEmailResponse,
  OrgMember,
} from './types';

// API base URL configuration
const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/dashboard-api';

// Demo mode state
let demoMode = !isFirebaseConfigured;

export const getDemoMode = () => demoMode;
export const setDemoMode = (enabled: boolean) => {
  demoMode = enabled;
};

// Helper for real API calls
async function fetchWithAuth<T>(
  endpoint: string,
  token: string | null,
  options: RequestInit = {}
): Promise<T> {
  const url = endpoint.startsWith('http') ? endpoint : `${BASE_URL}${endpoint}`;
  
  const headers = new Headers(options.headers || {});
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  
  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorMessage = `API error: ${response.status} ${response.statusText}`;
    const status = response.status;
    try {
      const errBody = (await response.json()) as { detail?: string };
      errorMessage = errBody.detail || errorMessage;
    } catch {
      // Ignored
    }
    const err = new Error(errorMessage) as any;
    err.status = status;
    throw err;
  }

  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Mock Data for Demo/Development Mode
// ---------------------------------------------------------------------------
const MOCK_USER: DashboardUser = {
  uid: 'demo-admin-uid-12345',
  email: 'admin@doceebot.com',
  name: 'Elena Rostova',
  picture: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&q=80&w=150',
};

const MOCK_ORGANIZATIONS = [
  {
    id: '1e9a2b8e-5b12-4d24-a13a-c8dfa4a275f1',
    name: 'Oakridge Agro Industries',
    created_at: '2026-02-15T08:30:00Z',
    member_count: 42,
    document_count: 14,
    work_log_count: 582,
    conversation_count: 120,
    active_session_count: 8,
  },
  {
    id: 'bc7f26d3-2a21-477d-b65f-4ea21394b9f2',
    name: 'Lakeside Logistical Partners',
    created_at: '2026-03-01T10:15:00Z',
    member_count: 24,
    document_count: 8,
    work_log_count: 312,
    conversation_count: 65,
    active_session_count: 3,
  },
  {
    id: '97f9fa42-df48-43d9-a790-db0e87b7a661',
    name: 'Green Valley Harvest Co.',
    created_at: '2026-04-10T14:45:00Z',
    member_count: 18,
    document_count: 5,
    work_log_count: 198,
    conversation_count: 42,
    active_session_count: 0,
  },
  {
    id: 'd9e03d42-ef11-47d0-a083-d5d8fb87a911',
    name: 'Savanna Timber & Forestry',
    created_at: '2026-05-20T09:00:00Z',
    member_count: 15,
    document_count: 3,
    work_log_count: 87,
    conversation_count: 19,
    active_session_count: 1,
  },
];

const MOCK_DOCUMENTS = [
  {
    id: 'd1c1c1c1-1111-4c4c-8c8c-111111111111',
    org_id: '1e9a2b8e-5b12-4d24-a13a-c8dfa4a275f1',
    organization_name: 'Oakridge Agro Industries',
    owner_user_id: 'u111-2222',
    owner_name: 'Marcus Vance',
    display_name: 'Daily Shift Log Report Template',
    filename: 'daily_shift_template.docx',
    document_kind: 'docx_template',
    content_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    source_type: 'upload',
    status: 'processed',
    size_bytes: 48512,
    summary: 'Standard shift template mapping [ShiftDate], [WorkerName], [TotalHours], [CompletedPlots], [TractorStatus], and [SupervisorSignoff]. Used for auto-generating supervisor summaries.',
    tags: ['shift-reports', 'agriculture', 'v1.4'],
    update_count: 3,
    created_at: '2026-02-16T11:00:00Z',
    updated_at: '2026-05-18T16:22:00Z',
  },
  {
    id: 'd2c2c2c2-2222-4c4c-8c8c-222222222222',
    org_id: '1e9a2b8e-5b12-4d24-a13a-c8dfa4a275f1',
    organization_name: 'Oakridge Agro Industries',
    owner_user_id: 'u111-2222',
    owner_name: 'Marcus Vance',
    display_name: 'Weekly Farm Operations Ledger Template',
    filename: 'weekly_farm_ops.xlsx',
    document_kind: 'xlsx_template',
    content_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    source_type: 'upload',
    status: 'processed',
    size_bytes: 92450,
    summary: 'Consolidated workbook containing worksheets for Harvest Metrics, Payroll Logs, and Equipment Maintenance Schedules. Maps directly to Postgres hourly work tables.',
    tags: ['accounting', 'xlsx-mapping', 'active'],
    update_count: 1,
    created_at: '2026-02-20T09:15:00Z',
    updated_at: '2026-02-20T09:15:00Z',
  },
  {
    id: 'd3c3c3c3-3333-4c4c-8c8c-333333333333',
    org_id: '1e9a2b8e-5b12-4d24-a13a-c8dfa4a275f1',
    organization_name: 'Oakridge Agro Industries',
    owner_user_id: null,
    owner_name: 'System Bot',
    display_name: 'Harvest Work Log - June 2026',
    filename: 'field_logs_jun26.xlsx',
    document_kind: 'xlsx_output',
    content_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    source_type: 'generation',
    status: 'generated',
    size_bytes: 145220,
    summary: 'Auto-generated ledger compiling 242 confirmed worker entries for June 2026. Generated via system cron, dispatched to supervisor WhatsApp chat.',
    tags: ['harvest', 'output-log', 'june-2026'],
    update_count: 0,
    created_at: '2026-07-01T00:05:00Z',
    updated_at: '2026-07-01T00:05:00Z',
  },
  {
    id: 'd4c4c4c4-4444-4c4c-8c8c-444444444444',
    org_id: 'bc7f26d3-2a21-477d-b65f-4ea21394b9f2',
    organization_name: 'Lakeside Logistical Partners',
    owner_user_id: 'u333-4444',
    owner_name: 'David Cole',
    display_name: 'Logistics Intake Sheet Template',
    filename: 'logistics_intake.xlsx',
    document_kind: 'xlsx_template',
    content_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    source_type: 'upload',
    status: 'processed',
    size_bytes: 34100,
    summary: 'Template mapping truck IDs, weighing scale weights, receipt OCR results, and warehouse bin indices. Integrates with the Telegram intake bot.',
    tags: ['logistics', 'ocr-mapping', 'v2'],
    update_count: 5,
    created_at: '2026-03-05T14:00:00Z',
    updated_at: '2026-06-25T10:45:00Z',
  },
  {
    id: 'd5c5c5c5-5555-4c4c-8c8c-555555555555',
    org_id: '97f9fa42-df48-43d9-a790-db0e87b7a661',
    organization_name: 'Green Valley Harvest Co.',
    owner_user_id: null,
    owner_name: 'System Bot',
    display_name: 'Outbound Delivery Summary Report',
    filename: 'delivery_summary_jun26.docx',
    document_kind: 'docx_output',
    content_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    source_type: 'generation',
    status: 'failed',
    size_bytes: null,
    summary: null,
    tags: ['error', 'june-2026'],
    update_count: 0,
    created_at: '2026-07-02T18:10:00Z',
    updated_at: '2026-07-02T18:10:00Z',
  },
];

const MOCK_ESCALATIONS = [
  {
    id: 'e1e1e1e1-1111-4e4e-9e9e-111111111111',
    conversation_id: 'c1c1c1c1-1111-4c4c-8c8c-111111111111',
    org_id: '1e9a2b8e-5b12-4d24-a13a-c8dfa4a275f1',
    organization_name: 'Oakridge Agro Industries',
    user_id: 'u111-2222',
    user_name: 'Marcus Vance',
    platform: 'whatsapp',
    report_text: 'Voice note transcription failed repeatedly. Worker sent a 3-minute voice message in highly dialectal Yoruba. The system encountered a timeout during the Gemini audio file analysis step.',
    status: 'pending',
    destination: 'developer-telegram-channel',
    error_text: 'Gemini API Error: 504 Gateway Timeout during content generation request.',
    turn_count: 8,
    work_log_count: 2,
    created_at: '2026-07-06T18:40:00Z',
    sent_at: '2026-07-06T18:40:05Z',
  },
  {
    id: 'e2e2e2e2-2222-4e4e-9e9e-222222222222',
    conversation_id: 'c2c2c2c2-2222-4c4c-8c8c-222222222222',
    org_id: 'bc7f26d3-2a21-477d-b65f-4ea21394b9f2',
    organization_name: 'Lakeside Logistical Partners',
    user_id: 'u333-5555',
    user_name: 'Sergei K.',
    platform: 'telegram',
    report_text: 'User uploaded an image receipt for diesel fuel. The OCR extraction output failed schema verification. Diesel volume was parsed as "fifty liters" (string) instead of a numeric float, breaking database constraints.',
    status: 'failed',
    destination: 'developer-email-alerts',
    error_text: 'SQLAlchemy ValidationError: Value "fifty liters" is not a valid float for column "quantity".',
    turn_count: 4,
    work_log_count: 0,
    created_at: '2026-07-06T15:20:00Z',
    sent_at: '2026-07-06T15:20:10Z',
  },
  {
    id: 'e3e3e3e3-3333-4e4e-9e9e-333333333333',
    conversation_id: 'c3c3c3c3-3333-4c4c-8c8c-333333333333',
    org_id: '97f9fa42-df48-43d9-a790-db0e87b7a661',
    organization_name: 'Green Valley Harvest Co.',
    user_id: 'u444-5555',
    user_name: 'Samuel Adebayo',
    platform: 'whatsapp',
    report_text: 'Double confirmation trigger. User replied "confirm" and "cancel" in rapid succession. Bot state locked up in a race condition inside the redis conversation lock wrapper.',
    status: 'resolved',
    destination: 'developer-telegram-channel',
    error_text: 'Redlock.LockAcquisitionError: Failed to acquire lock within timeout period.',
    turn_count: 12,
    work_log_count: 3,
    created_at: '2026-07-05T09:12:00Z',
    sent_at: '2026-07-05T09:12:12Z',
  },
];

const MOCK_LOGS = {
  conversations: [
    {
      conversation_id: 'c1c1c1c1-1111-4c4c-8c8c-111111111111',
      org_id: '1e9a2b8e-5b12-4d24-a13a-c8dfa4a275f1',
      organization_name: 'Oakridge Agro Industries',
      user_id: 'u111-2222',
      user_name: 'Marcus Vance',
      platform: 'whatsapp',
      status: 'active',
      started_at: '2026-07-06T18:00:00Z',
      last_message_at: '2026-07-06T18:40:00Z',
      turn_count: 5,
      work_log_count: 2,
      escalation_count: 1,
      turns: [
        {
          direction: 'inbound',
          platform: 'whatsapp',
          message_type: 'text',
          body_text: 'Hi bot, I am starting my shift today at 6 PM. Driving tractor T-14 in Plot C-2.',
          occurred_at: '2026-07-06T18:00:00Z',
          created_at: '2026-07-06T18:00:02Z',
          metadata: { ip_address: '127.0.0.1', is_voice: false },
        },
        {
          direction: 'outbound',
          platform: 'whatsapp',
          message_type: 'text',
          body_text: 'Good evening Marcus. I have logged your shift start at 6:00 PM. Tractor: T-14, Area: Plot C-2. Please send work updates or media. Let me know when you finish.',
          occurred_at: '2026-07-06T18:00:15Z',
          created_at: '2026-07-06T18:00:15Z',
          metadata: { llm_model: 'gemini-3.1-flash-lite', processing_time_ms: 850 },
        },
        {
          direction: 'inbound',
          platform: 'whatsapp',
          message_type: 'voice',
          body_text: '[Voice note transcription failed: Yoruba dialect timeout error]',
          occurred_at: '2026-07-06T18:38:00Z',
          created_at: '2026-07-06T18:38:05Z',
          metadata: { is_voice: true, duration_seconds: 180 },
        },
        {
          direction: 'outbound',
          platform: 'whatsapp',
          message_type: 'text',
          body_text: 'Marcus, I experienced a technical issue parsing your voice note. I have filed an escalation report to the system administrators. Please type your update in text format if possible.',
          occurred_at: '2026-07-06T18:40:00Z',
          created_at: '2026-07-06T18:40:00Z',
          metadata: { escalated: true },
        },
      ],
    },
    {
      conversation_id: 'c3c3c3c3-3333-4c4c-8c8c-333333333333',
      org_id: '97f9fa42-df48-43d9-a790-db0e87b7a661',
      organization_name: 'Green Valley Harvest Co.',
      user_id: 'u444-5555',
      user_name: 'Samuel Adebayo',
      platform: 'whatsapp',
      status: 'closed',
      started_at: '2026-07-05T08:00:00Z',
      last_message_at: '2026-07-05T09:15:00Z',
      turn_count: 5,
      work_log_count: 1,
      escalation_count: 0,
      turns: [
        {
          direction: 'inbound',
          platform: 'whatsapp',
          message_type: 'text',
          body_text: 'Started harvesting plot B-4 at 8:00 AM with a team of 5 workers.',
          occurred_at: '2026-07-05T08:00:00Z',
          created_at: '2026-07-05T08:00:01Z',
          metadata: {},
        },
        {
          direction: 'outbound',
          platform: 'whatsapp',
          message_type: 'text',
          body_text: 'Understood, Samuel. Logged start of harvest at Plot B-4 with a 5-man crew starting at 8:00 AM.',
          occurred_at: '2026-07-05T08:00:10Z',
          created_at: '2026-07-05T08:00:10Z',
          metadata: { llm_model: 'gemini-3.1-flash-lite' },
        },
        {
          direction: 'inbound',
          platform: 'whatsapp',
          message_type: 'text',
          body_text: 'We are finished. Total yield is 45 crates of tomatoes. tractor engine off.',
          occurred_at: '2026-07-05T09:10:00Z',
          created_at: '2026-07-05T09:10:02Z',
          metadata: {},
        },
        {
          direction: 'outbound',
          platform: 'whatsapp',
          message_type: 'text',
          body_text: 'Great work. I will draft a log: "Harvested 45 crates of tomatoes at Plot B-4 with team of 5". Please reply "confirm" to finalize this log, or reply with edits.',
          occurred_at: '2026-07-05T09:10:20Z',
          created_at: '2026-07-05T09:10:20Z',
          metadata: { llm_model: 'gemini-3.1-flash-lite' },
        },
        {
          direction: 'inbound',
          platform: 'whatsapp',
          message_type: 'text',
          body_text: 'confirm',
          occurred_at: '2026-07-05T09:15:00Z',
          created_at: '2026-07-05T09:15:01Z',
          metadata: {},
        },
        {
          direction: 'outbound',
          platform: 'whatsapp',
          message_type: 'text',
          body_text: 'Confirmed! Your work log has been saved and is pending supervisor report compilation. Enjoy the rest of your day, Samuel.',
          occurred_at: '2026-07-05T09:15:10Z',
          created_at: '2026-07-05T09:15:10Z',
          metadata: { action: 'confirm_log' },
        },
      ],
    },
  ],
};

const MOCK_TOKEN_USAGE: TokenUsageResponse = {
  generated_at: new Date().toISOString(),
  window_days: 30,
  note: 'Demo token counts are estimated from simulated redacted LLM audit payload sizes.',
  totals: {
    request_count: 318,
    success_count: 305,
    error_count: 13,
    input_tokens: 68420,
    output_tokens: 24350,
    total_tokens: 92770,
    average_total_tokens: 291.73,
    last_event_at: '2026-07-06T20:10:00Z',
    estimated: true,
  },
  by_model: [
    {
      provider: 'deepseek',
      model: 'deepseek-chat',
      purpose: null,
      request_count: 214,
      success_count: 207,
      error_count: 7,
      input_tokens: 42100,
      output_tokens: 18320,
      total_tokens: 60420,
      average_total_tokens: 282.34,
      first_seen_at: '2026-06-08T10:00:00Z',
      last_seen_at: '2026-07-06T20:10:00Z',
      estimated: true,
    },
    {
      provider: 'gemini',
      model: 'gemini-2.5-flash',
      purpose: null,
      request_count: 104,
      success_count: 98,
      error_count: 6,
      input_tokens: 26320,
      output_tokens: 6030,
      total_tokens: 32350,
      average_total_tokens: 311.06,
      first_seen_at: '2026-06-08T11:20:00Z',
      last_seen_at: '2026-07-06T18:38:00Z',
      estimated: true,
    },
  ],
  by_purpose: [
    {
      provider: 'all',
      model: 'all',
      purpose: 'chat_parse',
      request_count: 214,
      success_count: 207,
      error_count: 7,
      input_tokens: 42100,
      output_tokens: 18320,
      total_tokens: 60420,
      average_total_tokens: 282.34,
      first_seen_at: '2026-06-08T10:00:00Z',
      last_seen_at: '2026-07-06T20:10:00Z',
      estimated: true,
    },
    {
      provider: 'all',
      model: 'all',
      purpose: 'media_extraction',
      request_count: 104,
      success_count: 98,
      error_count: 6,
      input_tokens: 26320,
      output_tokens: 6030,
      total_tokens: 32350,
      average_total_tokens: 311.06,
      first_seen_at: '2026-06-08T11:20:00Z',
      last_seen_at: '2026-07-06T18:38:00Z',
      estimated: true,
    },
  ],
  daily: [
    { date: '2026-07-01', request_count: 38, input_tokens: 7800, output_tokens: 2600, total_tokens: 10400, error_count: 1, estimated: true },
    { date: '2026-07-02', request_count: 52, input_tokens: 10340, output_tokens: 3880, total_tokens: 14220, error_count: 2, estimated: true },
    { date: '2026-07-03', request_count: 44, input_tokens: 9550, output_tokens: 3200, total_tokens: 12750, error_count: 1, estimated: true },
    { date: '2026-07-04', request_count: 62, input_tokens: 12800, output_tokens: 4520, total_tokens: 17320, error_count: 3, estimated: true },
    { date: '2026-07-05', request_count: 70, input_tokens: 15100, output_tokens: 5200, total_tokens: 20300, error_count: 2, estimated: true },
    { date: '2026-07-06', request_count: 52, input_tokens: 12830, output_tokens: 4950, total_tokens: 17780, error_count: 4, estimated: true },
  ],
  recent: [
    {
      id: 'a1111111-1111-4111-8111-111111111111',
      conversation_id: 'c1c1c1c1-1111-4c4c-8c8c-111111111111',
      provider: 'deepseek',
      model: 'deepseek-chat',
      purpose: 'chat_parse',
      input_tokens: 255,
      output_tokens: 112,
      total_tokens: 367,
      status: 'success',
      created_at: '2026-07-06T20:10:00Z',
      estimated: true,
    },
    {
      id: 'a2222222-2222-4222-8222-222222222222',
      conversation_id: 'c1c1c1c1-1111-4c4c-8c8c-111111111111',
      provider: 'gemini',
      model: 'gemini-2.5-flash',
      purpose: 'media_extraction',
      input_tokens: 410,
      output_tokens: 58,
      total_tokens: 468,
      status: 'error',
      created_at: '2026-07-06T18:38:00Z',
      estimated: true,
    },
  ],
};

// ---------------------------------------------------------------------------
// API Methods
// ---------------------------------------------------------------------------

export const getMe = async (token: string | null): Promise<DashboardUser> => {
  if (demoMode) {
    return new Promise((resolve) => setTimeout(() => resolve(MOCK_USER), 500));
  }
  return fetchWithAuth<DashboardUser>('/me', token);
};

export const getOverview = async (token: string | null): Promise<OverviewResponse> => {
  if (demoMode) {
    return new Promise((resolve) =>
      setTimeout(
        () =>
          resolve({
            user: MOCK_USER,
            generated_at: new Date().toISOString(),
            cards: [
              { label: 'Organizations', value: MOCK_ORGANIZATIONS.length, helper: 'Tenants connected', tone: 'neutral' },
              { label: 'Total Users', value: 99, helper: 'Known bot users', tone: 'neutral' },
              { label: 'Documents', value: MOCK_DOCUMENTS.length, helper: 'Uploaded & generated files', tone: 'neutral' },
              { label: 'Active Sessions', value: 12, helper: '13-hour work spaces', tone: 'neutral' },
              { label: 'Escalations', value: 2, helper: 'Pending developer issues', tone: 'warning' },
            ],
            ux_metrics: {
              unconfirmed_draft_rate: 18.2,
              correction_rate: 8.5,
              fallback_rate: 4.1,
              messages_per_confirmed_log: 3.8,
              media_processing_events: 154,
              average_session_hours: 4.8,
              draft_logs: 14,
              confirmed_logs: 63,
            },
            recent_escalations: MOCK_ESCALATIONS.slice(0, 5),
            document_breakdown: [
              { label: 'docx_template', value: 2 },
              { label: 'xlsx_template', value: 2 },
              { label: 'xlsx_output', value: 1 },
            ],
            session_breakdown: [
              { label: 'active', value: 12 },
              { label: 'closed', value: 87 },
            ],
          }),
        600
      )
    );
  }
  return fetchWithAuth<OverviewResponse>('/overview', token);
};

export const getOrganizations = async (token: string | null): Promise<OrganizationsResponse> => {
  if (demoMode) {
    return new Promise((resolve) =>
      setTimeout(() => resolve({ organizations: MOCK_ORGANIZATIONS }), 400)
    );
  }
  return fetchWithAuth<OrganizationsResponse>('/organizations', token);
};

export const getDocuments = async (
  token: string | null,
  orgId?: string,
  status?: string
): Promise<DocumentsDashboardResponse> => {
  if (demoMode) {
    return new Promise((resolve) => {
      setTimeout(() => {
        let docs = [...MOCK_DOCUMENTS];
        if (orgId) {
          docs = docs.filter((d) => d.org_id === orgId);
        }
        if (status) {
          docs = docs.filter((d) => d.status === status);
        }
        resolve({ documents: docs });
      }, 500);
    });
  }
  
  const params = new URLSearchParams();
  if (orgId) params.append('org_id', orgId);
  if (status) params.append('status', status);
  
  const queryStr = params.toString() ? `?${params.toString()}` : '';
  return fetchWithAuth<DocumentsDashboardResponse>(`/documents${queryStr}`, token);
};

export const getEscalations = async (
  token: string | null,
  status?: string
): Promise<EscalationsResponse> => {
  if (demoMode) {
    return new Promise((resolve) => {
      setTimeout(() => {
        let escs = [...MOCK_ESCALATIONS];
        if (status) {
          escs = escs.filter((e) => e.status === status);
        }
        resolve({ escalations: escs });
      }, 400);
    });
  }
  
  const params = new URLSearchParams();
  if (status) params.append('status', status);
  
  const queryStr = params.toString() ? `?${params.toString()}` : '';
  return fetchWithAuth<EscalationsResponse>(`/escalations${queryStr}`, token);
};

export const getLogs = async (
  token: string | null,
  password?: string
): Promise<LogsResponse> => {
  if (demoMode) {
    return new Promise((resolve, reject) => {
      setTimeout(() => {
        if (!password || password !== 'demo') {
          reject(new Error('Invalid logs password. (Hint: Use "demo" in Demo Mode)'));
          return;
        }
        resolve(MOCK_LOGS as LogsResponse);
      }, 700);
    });
  }
  
  const headers = new Headers();
  if (password) {
    headers.set('X-Logs-Password', password);
  }
  
  return fetchWithAuth<LogsResponse>('/logs', token, { headers });
};

export const getTokenUsage = async (
  token: string | null,
  windowDays = 30
): Promise<TokenUsageResponse> => {
  if (demoMode) {
    return new Promise((resolve) =>
      setTimeout(
        () =>
          resolve({
            ...MOCK_TOKEN_USAGE,
            generated_at: new Date().toISOString(),
            window_days: windowDays,
          }),
        500
      )
    );
  }

  const params = new URLSearchParams({ window_days: String(windowDays) });
  return fetchWithAuth<TokenUsageResponse>(`/token-usage?${params.toString()}`, token);
};

const MOCK_SEARCH_RESULTS = [
  {
    org_id: '1e9a2b8e-5b12-4d24-a13a-c8dfa4a275f1',
    user_id: 'u111-2222',
    source_id: 'w-mock-1',
    session_id: 'c1c1c1c1-1111-4c4c-8c8c-111111111111',
    score: 0.92,
    snippet: 'Completed plowing Plot C-2 using tractor T-14. Engine hours logged: 4.2. Supervisor signed off on completion.',
    result_type: 'work_log',
    work_log_title: 'Plot C-2 Tractor Plowing',
    work_log_date: '2026-07-06',
    turn_body_preview: null,
    session_started_at: '2026-07-06T18:00:00Z',
    session_status: 'active',
    display_title: 'Plot C-2 Tractor Plowing',
    display_date: '2026-07-06',
  },
  {
    org_id: '1e9a2b8e-5b12-4d24-a13a-c8dfa4a275f1',
    user_id: 'u111-2222',
    source_id: 't-mock-1',
    session_id: 'c1c1c1c1-1111-4c4c-8c8c-111111111111',
    score: 0.81,
    snippet: 'Hi bot, I am starting my shift today at 6 PM. Driving tractor T-14 in Plot C-2.',
    result_type: 'turn',
    work_log_title: null,
    work_log_date: null,
    turn_body_preview: 'Hi bot, I am starting my shift today at 6 PM. Driving tractor T-14 in Plot C-2.',
    session_started_at: '2026-07-06T18:00:00Z',
    session_status: 'active',
    display_title: 'Hi bot, I am starting my shift today at 6 PM. Driving tractor T-14...',
    display_date: '2026-07-06T18:00:00Z',
  },
  {
    org_id: '97f9fa42-df48-43d9-a790-db0e87b7a661',
    user_id: 'u444-5555',
    source_id: 'w-mock-2',
    session_id: 'c3c3c3c3-3333-4c4c-8c8c-333333333333',
    score: 0.76,
    snippet: 'Harvested 45 crates of tomatoes at Plot B-4 with a team of 5 workers. Tractor engine turned off and locked.',
    result_type: 'work_log',
    work_log_title: 'Harvesting Tomatoes - Plot B-4',
    work_log_date: '2026-07-05',
    turn_body_preview: null,
    session_started_at: '2026-07-05T08:00:00Z',
    session_status: 'closed',
    display_title: 'Harvesting Tomatoes - Plot B-4',
    display_date: '2026-07-05',
  },
  {
    org_id: '1e9a2b8e-5b12-4d24-a13a-c8dfa4a275f1',
    user_id: 'u111-2222',
    source_id: 'c1c1c1c1-1111-4c4c-8c8c-111111111111',
    session_id: 'c1c1c1c1-1111-4c4c-8c8c-111111111111',
    score: 0.65,
    snippet: 'Active conversation session for Marcus Vance. 5 turns logged. Includes pending Yoruba language voice note escalation.',
    result_type: 'session',
    work_log_title: null,
    work_log_date: null,
    turn_body_preview: null,
    session_started_at: '2026-07-06T18:00:00Z',
    session_status: 'active',
    display_title: 'Marcus Vance - Tractor Operations',
    display_date: '2026-07-06T18:00:00Z',
  },
  {
    org_id: 'bc7f26d3-2a21-477d-b65f-4ea21394b9f2',
    user_id: 'u333-5555',
    source_id: 'w-mock-3',
    session_id: 'c2c2c2c2-2222-4c4c-8c8c-222222222222',
    score: 0.88,
    snippet: 'Intake of diesel fuel for truck fleet. Image OCR processed, parsed 50 liters. System validation flagged string format error.',
    result_type: 'work_log',
    work_log_title: 'Diesel Fuel Intake Receipt OCR',
    work_log_date: '2026-07-06',
    turn_body_preview: null,
    session_started_at: '2026-07-06T15:20:00Z',
    session_status: 'active',
    display_title: 'Diesel Fuel Intake Receipt OCR',
    display_date: '2026-07-06',
  },
  {
    org_id: 'bc7f26d3-2a21-477d-b65f-4ea21394b9f2',
    user_id: 'u333-5555',
    source_id: 't-mock-2',
    session_id: 'c2c2c2c2-2222-4c4c-8c8c-222222222222',
    score: 0.72,
    snippet: 'Truck intake completed for vehicle LL-902. Weight: 14.2 tons. OCR extracted from scale receipt.',
    result_type: 'turn',
    work_log_title: null,
    work_log_date: null,
    turn_body_preview: 'Truck intake completed for vehicle LL-902. Weight: 14.2 tons. OCR extracted from scale receipt.',
    session_started_at: '2026-07-06T15:20:00Z',
    session_status: 'active',
    display_title: 'Truck intake completed for vehicle LL-902. Weight: 14.2 tons...',
    display_date: '2026-07-06T15:20:00Z',
  }
];

export const searchSessions = async (
  token: string | null,
  q: string,
  orgId: string,
  userId?: string,
  limit = 10
): Promise<SessionSearchResponse> => {
  if (demoMode) {
    return new Promise((resolve) => {
      setTimeout(() => {
        let filtered = MOCK_SEARCH_RESULTS.filter((item) => item.org_id === orgId);

        if (userId) {
          filtered = filtered.filter((item) => item.user_id === userId);
        }

        const queryLower = q.toLowerCase().trim();
        if (queryLower) {
          filtered = filtered.filter(
            (item) =>
              item.snippet.toLowerCase().includes(queryLower) ||
              item.display_title.toLowerCase().includes(queryLower) ||
              (item.work_log_title && item.work_log_title.toLowerCase().includes(queryLower)) ||
              (item.turn_body_preview && item.turn_body_preview.toLowerCase().includes(queryLower))
          );
        }

        resolve({
          query: q,
          org_id: orgId,
          user_id: userId || null,
          results: filtered.slice(0, limit),
        });
      }, 500);
    });
  }

  const params = new URLSearchParams({
    q,
    org_id: orgId,
  });
  if (userId) {
    params.append('user_id', userId);
  }
  params.append('limit', String(limit));

  return fetchWithAuth<SessionSearchResponse>(`/search?${params.toString()}`, token);
};

// Mock admin users data for demo mode
const mockAdminMembers: Record<string, OrgMember[]> = {
  '1e9a2b8e-5b12-4d24-a13a-c8dfa4a275f1': [
    {
      user_id: 'u111-2222',
      display_name: 'Marcus Vance',
      phone_number: '+15550001',
      telegram_user_id: null,
      role: 'worker',
      created_at: '2026-02-16T11:00:00Z',
    },
    {
      user_id: 'u111-3333',
      display_name: 'Elena Rostova',
      phone_number: '+15550002',
      telegram_user_id: 'elena_rostova',
      role: 'org_admin',
      created_at: '2026-02-15T08:30:00Z',
    }
  ],
  'bc7f26d3-2a21-477d-b65f-4ea21394b9f2': [
    {
      user_id: 'u333-4444',
      display_name: 'David Cole',
      phone_number: '+15550003',
      telegram_user_id: null,
      role: 'manager',
      created_at: '2026-03-05T14:00:00Z',
    },
    {
      user_id: 'u333-5555',
      display_name: 'Sergei K.',
      phone_number: null,
      telegram_user_id: 'sergei_k',
      role: 'supervisor',
      created_at: '2026-03-01T10:15:00Z',
    }
  ],
  '97f9fa42-df48-43d9-a790-db0e87b7a661': [
    {
      user_id: 'u444-5555',
      display_name: 'Samuel Adebayo',
      phone_number: '+15550004',
      telegram_user_id: null,
      role: 'worker',
      created_at: '2026-04-10T14:45:00Z',
    }
  ],
  'd9e03d42-ef11-47d0-a083-d5d8fb87a911': [
    {
      user_id: 'u555-6666',
      display_name: 'Timber Supervisor',
      phone_number: '+15550005',
      telegram_user_id: 'timber_super',
      role: 'supervisor',
      created_at: '2026-05-20T09:00:00Z',
    }
  ]
};

export const getAdminAccess = async (token: string | null): Promise<AdminAccessResponse> => {
  if (demoMode) {
    return new Promise((resolve) =>
      setTimeout(() => {
        resolve({
          linked_user_id: 'demo-admin-uid-12345',
          linked_user_name: 'Elena Rostova',
          linked_user_email: 'admin@doceebot.com',
          organizations: MOCK_ORGANIZATIONS.map(org => ({
            id: org.id,
            name: org.name,
            role: 'org_admin',
            member_count: mockAdminMembers[org.id]?.length || 0,
          }))
        });
      }, 400)
    );
  }
  return fetchWithAuth<AdminAccessResponse>('/admin/access', token);
};

export const getAdminUsers = async (
  token: string | null,
  orgId: string
): Promise<AdminUsersResponse> => {
  if (demoMode) {
    return new Promise((resolve) =>
      setTimeout(() => {
        const org = MOCK_ORGANIZATIONS.find(o => o.id === orgId);
        resolve({
          org_id: orgId,
          organization_name: org ? org.name : 'Unknown Organization',
          members: mockAdminMembers[orgId] || [],
        });
      }, 400)
    );
  }
  return fetchWithAuth<AdminUsersResponse>(`/admin/users?org_id=${encodeURIComponent(orgId)}`, token);
};

export const addAdminUser = async (
  token: string | null,
  payload: AddMemberPayload
): Promise<AddMemberResponse> => {
  if (demoMode) {
    return new Promise((resolve, reject) =>
      setTimeout(() => {
        // Simulating some validations (e.g. empty identifier conflict)
        if (!payload.identifier.trim()) {
          const err = new Error('Identifier cannot be empty') as any;
          err.status = 400;
          reject(err);
          return;
        }

        const org = MOCK_ORGANIZATIONS.find(o => o.id === payload.org_id);
        if (!org) {
          const err = new Error('Organization not found') as any;
          err.status = 404;
          reject(err);
          return;
        }

        // Simulating a 409 conflict scenario or 403 authorization scenario if specific test conditions are met.
        // Let's allow users to specify "conflict" or similar in name/identifier if they want to test errors:
        if (payload.identifier.includes('conflict')) {
          const err = new Error('A conflict occurred: User/membership already exists with a different conflict state.') as any;
          err.status = 409;
          reject(err);
          return;
        }
        if (payload.identifier.includes('forbidden')) {
          const err = new Error('Forbidden: You do not have permission to modify this organization.') as any;
          err.status = 403;
          reject(err);
          return;
        }

        const members = mockAdminMembers[payload.org_id] || [];
        const isWhatsapp = payload.platform === 'whatsapp';
        
        // Find if a member with this identifier/platform already exists
        const existingMemberIndex = members.findIndex(m => {
          if (isWhatsapp) {
            return m.phone_number === payload.identifier;
          } else {
            return m.telegram_user_id === payload.identifier;
          }
        });

        if (existingMemberIndex !== -1) {
          const existingMember = members[existingMemberIndex];
          const roleChanged = existingMember.role !== payload.role;
          
          // Update details
          existingMember.role = payload.role;
          if (payload.display_name) {
            existingMember.display_name = payload.display_name;
          }
          
          resolve({
            org_id: payload.org_id,
            organization_name: org.name,
            user: existingMember,
            created_user: false,
            created_membership: false,
            updated_membership_role: roleChanged,
          });
        } else {
          const newUserId = 'u-mock-' + Math.random().toString(36).substr(2, 9);
          const newMember: OrgMember = {
            user_id: newUserId,
            display_name: payload.display_name || payload.identifier,
            phone_number: isWhatsapp ? payload.identifier : null,
            telegram_user_id: isWhatsapp ? null : payload.identifier,
            role: payload.role,
            created_at: new Date().toISOString(),
          };

          mockAdminMembers[payload.org_id] = [...members, newMember];
          // Update the MOCK_ORGANIZATIONS count
          org.member_count += 1;

          resolve({
            org_id: payload.org_id,
            organization_name: org.name,
            user: newMember,
            created_user: true,
            created_membership: true,
            updated_membership_role: false,
          });
        }
      }, 500)
    );
  }

  return fetchWithAuth<AddMemberResponse>('/admin/users', token, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
};


export const linkAdminEmail = async (
  token: string | null,
  payload: LinkEmailPayload
): Promise<LinkEmailResponse> => {
  if (demoMode) {
    return new Promise((resolve, reject) => {
      setTimeout(() => {
        if (!payload.email.trim() || !payload.email.includes('@')) {
          const err = new Error('A valid dashboard login email is required') as any;
          err.status = 422;
          reject(err);
          return;
        }
        const org = MOCK_ORGANIZATIONS.find(o => o.id === payload.org_id);
        if (!org) {
          const err = new Error('Organization not found') as any;
          err.status = 404;
          reject(err);
          return;
        }
        if (payload.identifier.includes('forbidden')) {
          const err = new Error('Forbidden: You do not have permission to manage this organization.') as any;
          err.status = 403;
          reject(err);
          return;
        }
        if (payload.identifier.includes('conflict')) {
          const err = new Error('That email or identifier is already linked to a different user.') as any;
          err.status = 409;
          reject(err);
          return;
        }

        const isWhatsapp = payload.platform === 'whatsapp';
        const members = mockAdminMembers[payload.org_id] || [];
        let member = members.find(m =>
          isWhatsapp ? m.phone_number === payload.identifier : m.telegram_user_id === payload.identifier
        );
        const createdUser = !member;
        if (!member) {
          member = {
            user_id: 'u-link-' + Math.random().toString(36).slice(2, 11),
            display_name: payload.display_name || payload.identifier,
            phone_number: isWhatsapp ? payload.identifier : null,
            telegram_user_id: isWhatsapp ? null : payload.identifier,
            role: payload.role || 'org_admin',
            created_at: new Date().toISOString(),
          };
          mockAdminMembers[payload.org_id] = [...members, member];
        } else if (payload.display_name) {
          member.display_name = payload.display_name;
        }
        if (member.role !== (payload.role || 'org_admin')) {
          member.role = payload.role || 'org_admin';
        }

        resolve({
          org_id: payload.org_id,
          organization_name: org.name,
          user: member,
          email: payload.email.trim().toLowerCase(),
          email_previously_set: false,
          created_user: createdUser,
          created_membership: createdUser,
          updated_membership_role: !createdUser,
          updated_membership_email: true,
        });
      }, 500);
    });
  }
  return fetchWithAuth<LinkEmailResponse>('/admin/link-email', token, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
};

