import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, BarChart3, Clock3, Cpu, Gauge, RefreshCw, WalletCards } from 'lucide-react';
import { getTokenUsage } from '../api';
import { useAuth } from '../contexts/AuthContext';
import type { TokenUsageBreakdownRow, TokenUsageDailyRow, TokenUsageResponse } from '../types';

const TOKEN_WINDOWS = [7, 30, 90, 365];

const numberFormatter = new Intl.NumberFormat(undefined);

function formatNumber(value: number | null | undefined): string {
  return numberFormatter.format(Math.round(value || 0));
}

function formatAverage(value: number | null | undefined): string {
  return numberFormatter.format(Number((value || 0).toFixed(2)));
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  return new Date(value).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

function formatDay(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  });
}

function statusBadge(status: string): React.ReactNode {
  return status === 'error' ? (
    <span className="badge badge-error">error</span>
  ) : (
    <span className="badge badge-success">success</span>
  );
}

function DailyTokenBar({ day, maxTokens }: { day: TokenUsageDailyRow; maxTokens: number }) {
  const width = maxTokens > 0 ? Math.max(4, Math.round((day.total_tokens / maxTokens) * 100)) : 0;
  const inputWidth = day.total_tokens > 0 ? Math.round((day.input_tokens / day.total_tokens) * width) : 0;
  const outputWidth = Math.max(0, width - inputWidth);

  return (
    <div className="token-day-row">
      <div className="token-day-label">{formatDay(day.date)}</div>
      <div className="token-bar-track" aria-label={`${day.date}: ${day.total_tokens} estimated tokens`}>
        <div className="token-bar-input" style={{ width: `${inputWidth}%` }} />
        <div className="token-bar-output" style={{ width: `${outputWidth}%` }} />
      </div>
      <div className="token-day-value">{formatNumber(day.total_tokens)}</div>
    </div>
  );
}

function BreakdownTable({ rows }: { rows: TokenUsageBreakdownRow[] }) {
  return (
    <div className="table-wrapper">
      <table className="data-table">
        <thead>
          <tr>
            <th>Provider / Model</th>
            <th>Purpose</th>
            <th>Requests</th>
            <th>Input</th>
            <th>Output</th>
            <th>Total</th>
            <th>Avg / Req</th>
            <th>Last Seen</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.provider}-${row.model}-${row.purpose || 'all'}`}>
              <td>
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  <strong style={{ textTransform: 'capitalize' }}>{row.provider}</strong>
                  <span style={{ color: 'var(--brown-500)', fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>
                    {row.model}
                  </span>
                </div>
              </td>
              <td>
                <span className="badge badge-info" style={{ fontFamily: 'var(--font-mono)' }}>
                  {row.purpose || 'all'}
                </span>
              </td>
              <td>{formatNumber(row.request_count)}</td>
              <td>{formatNumber(row.input_tokens)}</td>
              <td>{formatNumber(row.output_tokens)}</td>
              <td style={{ fontWeight: 700 }}>{formatNumber(row.total_tokens)}</td>
              <td>{formatAverage(row.average_total_tokens)}</td>
              <td>{formatDateTime(row.last_seen_at)}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={8} style={{ textAlign: 'center', color: 'var(--brown-400)', padding: '2rem' }}>
                No LLM audit rows found for this window.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export const TokenUsageView: React.FC = () => {
  const { token } = useAuth();
  const [usage, setUsage] = useState<TokenUsageResponse | null>(null);
  const [windowDays, setWindowDays] = useState(30);
  const [refreshKey, setRefreshKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getTokenUsage(token, windowDays);
        if (!cancelled) {
          setUsage(data);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load token usage.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [token, windowDays, refreshKey]);

  const maxDailyTokens = useMemo(
    () => Math.max(0, ...(usage?.daily.map((day) => day.total_tokens) || [])),
    [usage]
  );

  const inputShare = usage && usage.totals.total_tokens > 0
    ? Math.round((usage.totals.input_tokens / usage.totals.total_tokens) * 100)
    : 0;
  const errorRate = usage && usage.totals.request_count > 0
    ? Math.round((usage.totals.error_count / usage.totals.request_count) * 1000) / 10
    : 0;

  return (
    <div className="fade-in">
      <div className="section-header">
        <div>
          <h1>Token Usage</h1>
          <p>Monitor LLM consumption by model, purpose, day, and recent audit request.</p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <select
            className="form-select"
            value={windowDays}
            onChange={(event) => setWindowDays(Number(event.target.value))}
            style={{ width: '160px' }}
          >
            {TOKEN_WINDOWS.map((days) => (
              <option key={days} value={days}>
                Last {days} days
              </option>
            ))}
          </select>
          <button className="btn btn-secondary" onClick={() => setRefreshKey((key) => key + 1)}>
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>
      </div>

      {loading && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '45vh', gap: '1rem' }}>
          <div className="spinner" style={{ width: '40px', height: '40px', borderWidth: '4px' }} />
          <p style={{ color: 'var(--brown-500)' }}>Calculating token consumption...</p>
        </div>
      )}

      {!loading && error && (
        <div className="glass-card" style={{ borderLeft: '4px solid var(--status-error-text)', background: 'var(--status-error-bg)' }}>
          <p style={{ color: 'var(--status-error-text)', fontWeight: 700 }}>Could not load token usage</p>
          <p style={{ color: 'var(--status-error-text)' }}>{error}</p>
        </div>
      )}

      {!loading && usage && (
        <>
          <div className="glass-card token-usage-note">
            <AlertTriangle size={18} />
            <span>{usage.note}</span>
          </div>

          <div className="metrics-grid">
            <div className="glass-card metric-card">
              <span className="metric-label">Total tokens</span>
              <span className="metric-value">{formatNumber(usage.totals.total_tokens)}</span>
              <span className="metric-helper">Estimated across {usage.window_days} days</span>
            </div>
            <div className="glass-card metric-card">
              <span className="metric-label">LLM requests</span>
              <span className="metric-value">{formatNumber(usage.totals.request_count)}</span>
              <span className="metric-helper">{formatNumber(usage.totals.success_count)} successful requests</span>
            </div>
            <div className="glass-card metric-card">
              <span className="metric-label">Avg / request</span>
              <span className="metric-value">{formatAverage(usage.totals.average_total_tokens)}</span>
              <span className="metric-helper">Estimated tokens per audit event</span>
            </div>
            <div className={`glass-card metric-card ${usage.totals.error_count > 0 ? 'warning' : ''}`}>
              <span className="metric-label">Error rate</span>
              <span className="metric-value">{errorRate}%</span>
              <span className="metric-helper">{formatNumber(usage.totals.error_count)} failed LLM events</span>
            </div>
          </div>

          <div className="dashboard-row">
            <div className="glass-card">
              <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
                <BarChart3 size={18} style={{ color: 'var(--accent-gold)' }} />
                Daily Consumption Trend
              </h3>
              <div className="token-chart-legend">
                <span><i className="legend-dot input" />Input estimate</span>
                <span><i className="legend-dot output" />Output estimate</span>
              </div>
              <div className="token-chart">
                {usage.daily.map((day) => (
                  <DailyTokenBar key={day.date} day={day} maxTokens={maxDailyTokens} />
                ))}
                {usage.daily.length === 0 && (
                  <div className="empty-state" style={{ minHeight: '220px' }}>
                    <BarChart3 className="empty-state-icon" size={42} />
                    <p>No daily usage yet for this window.</p>
                  </div>
                )}
              </div>
            </div>

            <div className="glass-card">
              <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
                <Gauge size={18} style={{ color: 'var(--accent-gold)' }} />
                Consumption Mix
              </h3>
              <div className="ux-metric-item">
                <span className="ux-metric-title">Input Share</span>
                <span className="ux-metric-val">{inputShare}%</span>
              </div>
              <div className="ux-metric-item">
                <span className="ux-metric-title">Input Tokens</span>
                <span className="ux-metric-val">{formatNumber(usage.totals.input_tokens)}</span>
              </div>
              <div className="ux-metric-item">
                <span className="ux-metric-title">Output Tokens</span>
                <span className="ux-metric-val">{formatNumber(usage.totals.output_tokens)}</span>
              </div>
              <div className="ux-metric-item">
                <span className="ux-metric-title">Last LLM Event</span>
                <span className="ux-metric-val" style={{ fontSize: '0.85rem', textAlign: 'right' }}>
                  {formatDateTime(usage.totals.last_event_at)}
                </span>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '1.25rem' }}>
                {usage.by_purpose.map((row) => (
                  <span key={row.purpose || 'all'} className="badge badge-info" style={{ textTransform: 'none' }}>
                    {row.purpose || 'all'} · {formatNumber(row.total_tokens)}
                  </span>
                ))}
              </div>
            </div>
          </div>

          <div className="glass-card" style={{ marginBottom: '2rem' }}>
            <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
              <Cpu size={18} style={{ color: 'var(--accent-gold)' }} />
              Usage by Provider and Model
            </h3>
            <BreakdownTable rows={usage.by_model} />
          </div>

          <div className="glass-card">
            <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
              <Clock3 size={18} style={{ color: 'var(--accent-gold)' }} />
              Recent LLM Audit Events
            </h3>
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Created</th>
                    <th>Provider</th>
                    <th>Purpose</th>
                    <th>Input</th>
                    <th>Output</th>
                    <th>Total</th>
                    <th>Status</th>
                    <th>Conversation</th>
                  </tr>
                </thead>
                <tbody>
                  {usage.recent.map((row) => (
                    <tr key={row.id}>
                      <td>{formatDateTime(row.created_at)}</td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                          <WalletCards size={14} style={{ color: 'var(--brown-500)' }} />
                          <span style={{ textTransform: 'capitalize', fontWeight: 700 }}>{row.provider}</span>
                        </div>
                        <span style={{ color: 'var(--brown-500)', fontFamily: 'var(--font-mono)', fontSize: '0.72rem' }}>
                          {row.model}
                        </span>
                      </td>
                      <td><span className="badge badge-info" style={{ fontFamily: 'var(--font-mono)' }}>{row.purpose}</span></td>
                      <td>{formatNumber(row.input_tokens)}</td>
                      <td>{formatNumber(row.output_tokens)}</td>
                      <td style={{ fontWeight: 700 }}>{formatNumber(row.total_tokens)}</td>
                      <td>{statusBadge(row.status)}</td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem' }}>
                        {row.conversation_id ? row.conversation_id.slice(0, 8) : '—'}
                      </td>
                    </tr>
                  ))}
                  {usage.recent.length === 0 && (
                    <tr>
                      <td colSpan={8} style={{ textAlign: 'center', color: 'var(--brown-400)', padding: '2rem' }}>
                        No recent LLM audit events found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
