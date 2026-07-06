/* oxlint-disable react-hooks/exhaustive-deps */
import React, { useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import {
  getOverview,
  getOrganizations,
  getDocuments,
  getEscalations,
} from '../api';
import type {
  OverviewResponse,
  OrganizationDashboardRow,
  DocumentDashboardRow,
  EscalationDashboardRow,
} from '../types';
import {
  Building2,
  RefreshCw,
  Sparkles,
  Eye,
} from 'lucide-react';

export const DashboardView: React.FC = () => {
  const { token } = useAuth();
  
  // States
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [organizations, setOrganizations] = useState<OrganizationDashboardRow[]>([]);
  const [documents, setDocuments] = useState<DocumentDashboardRow[]>([]);
  const [escalations, setEscalations] = useState<EscalationDashboardRow[]>([]);
  
  const [activeTab, setActiveTab] = useState<'orgs' | 'docs' | 'escalations'>('orgs');
  const [loading, setLoading] = useState(true);
  const [tabLoading, setTabLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [docOrgFilter, setDocOrgFilter] = useState<string>('');
  const [docStatusFilter, setDocStatusFilter] = useState<string>('');
  const [escStatusFilter, setEscStatusFilter] = useState<string>('');

  // Selected Detail Modals
  const [selectedDoc, setSelectedDoc] = useState<DocumentDashboardRow | null>(null);
  const [selectedEsc, setSelectedEsc] = useState<EscalationDashboardRow | null>(null);

  const fetchOverviewData = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getOverview(token);
      setOverview(data);
    } catch (err: any) {
      console.error(err);
      setError(err.message || 'Failed to load overview metrics.');
    } finally {
      setLoading(false);
    }
  };

  const fetchTabData = async () => {
    setTabLoading(true);
    try {
      if (activeTab === 'orgs') {
        const res = await getOrganizations(token);
        setOrganizations(res.organizations);
      } else if (activeTab === 'docs') {
        const res = await getDocuments(token, docOrgFilter || undefined, docStatusFilter || undefined);
        setDocuments(res.documents);
      } else if (activeTab === 'escalations') {
        const res = await getEscalations(token, escStatusFilter || undefined);
        setEscalations(res.escalations);
      }
    } catch (err: any) {
      console.error(err);
      // We don't block the main UI, just show a warning
    } finally {
      setTabLoading(false);
    }
  };

  // oxlint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    fetchOverviewData();
  }, [token]);

  // oxlint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    fetchTabData();
  }, [activeTab, docOrgFilter, docStatusFilter, escStatusFilter, token]);

  const handleRefreshAll = () => {
    fetchOverviewData();
    fetchTabData();
  };

  const getStatusBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case 'processed':
      case 'generated':
      case 'resolved':
      case 'confirmed':
        return <span className="badge badge-success">{status}</span>;
      case 'pending':
      case 'draft':
      case 'processing':
        return <span className="badge badge-warning">{status}</span>;
      case 'failed':
      case 'error':
        return <span className="badge badge-error">{status}</span>;
      default:
        return <span className="badge badge-info">{status}</span>;
    }
  };

  const formatBytes = (bytes: number | null) => {
    if (bytes === null || bytes === undefined) return 'N/A';
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '—';
    return new Date(dateStr).toLocaleString(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '60vh', gap: '1rem' }}>
        <div className="spinner" style={{ width: '40px', height: '40px', borderWidth: '4px' }} />
        <p style={{ color: 'var(--brown-500)' }}>Brewing dashboard overview...</p>
      </div>
    );
  }

  return (
    <div className="fade-in">
      {/* Top Banner */}
      <div className="section-header">
        <div>
          <h1>System Overview</h1>
          <p>Real-time metrics, document mapping pipelines, and channel activity.</p>
        </div>
        <button className="btn btn-secondary" onClick={handleRefreshAll}>
          <RefreshCw size={16} />
          Refresh Data
        </button>
      </div>

      {error && (
        <div className="glass-card" style={{ borderLeft: '4px solid var(--status-error-text)', marginBottom: '2rem', background: 'var(--status-error-bg)' }}>
          <p style={{ color: 'var(--status-error-text)', fontWeight: 'bold' }}>Error Loading Data</p>
          <p style={{ color: 'var(--status-error-text)' }}>{error}</p>
        </div>
      )}

      {/* Metrics Cards Grid */}
      {overview && (
        <div className="metrics-grid">
          {overview.cards.map((card, idx) => {
            const isWarning = card.tone === 'warning' && Number(card.value) > 0;
            return (
              <div key={idx} className={`glass-card metric-card ${isWarning ? 'warning' : ''}`}>
                <span className="metric-label">{card.label}</span>
                <span className="metric-value">{card.value}</span>
                <span className="metric-helper">{card.helper}</span>
              </div>
            );
          })}
        </div>
      )}

      {/* Second Row: UX Metrics & Document Breakdown */}
      {overview && (
        <div className="dashboard-row">
          {/* UX Metrics Card */}
          <div className="glass-card">
            <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
              <Sparkles size={18} style={{ color: 'var(--accent-gold)' }} />
              UX &amp; AI Quality Indices
            </h3>
            <div className="metrics-row" style={{ gridTemplateColumns: '1fr 1fr', gap: '1.5rem', marginBottom: 0 }}>
              <div>
                <div className="ux-metric-item">
                  <span className="ux-metric-title">Correction Rate</span>
                  <span className="ux-metric-val">{overview.ux_metrics.correction_rate}%</span>
                </div>
                <div className="ux-metric-item">
                  <span className="ux-metric-title">Parser Fallback Rate</span>
                  <span className="ux-metric-val">{overview.ux_metrics.fallback_rate}%</span>
                </div>
                <div className="ux-metric-item">
                  <span className="ux-metric-title">Unconfirmed Drafts</span>
                  <span className="ux-metric-val">{overview.ux_metrics.unconfirmed_draft_rate}%</span>
                </div>
                <div className="ux-metric-item">
                  <span className="ux-metric-title">Avg Session Duration</span>
                  <span className="ux-metric-val">{overview.ux_metrics.average_session_hours} hrs</span>
                </div>
              </div>
              
              <div>
                <div className="ux-metric-item">
                  <span className="ux-metric-title">Media Auditing Events</span>
                  <span className="ux-metric-val">{overview.ux_metrics.media_processing_events}</span>
                </div>
                <div className="ux-metric-item">
                  <span className="ux-metric-title">Messages per Log</span>
                  <span className="ux-metric-val">{overview.ux_metrics.messages_per_confirmed_log}</span>
                </div>
                <div className="ux-metric-item">
                  <span className="ux-metric-title">Draft Work Logs</span>
                  <span className="ux-metric-val">{overview.ux_metrics.draft_logs}</span>
                </div>
                <div className="ux-metric-item">
                  <span className="ux-metric-title">Confirmed Work Logs</span>
                  <span className="ux-metric-val">{overview.ux_metrics.confirmed_logs}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Breakdown Card */}
          <div className="glass-card">
            <h3>Document Inventory</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {overview.document_breakdown.map((doc, idx) => {
                const totalDocs = overview.document_breakdown.reduce((sum, item) => sum + (item.value as number), 0);
                const percent = totalDocs > 0 ? Math.round(((doc.value as number) * 100) / totalDocs) : 0;
                return (
                  <div key={idx} className="breakdown-item">
                    <div className="breakdown-info">
                      <span className="breakdown-label" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{String(doc.label)}</span>
                      <span className="breakdown-value">{String(doc.value)}</span>
                    </div>
                    <div className="progress-bar-bg">
                      <div className="progress-bar" style={{ width: `${percent}%`, backgroundColor: 'var(--brown-700)' }} />
                    </div>
                  </div>
                );
              })}
              {overview.document_breakdown.length === 0 && (
                <p style={{ color: 'var(--brown-400)', textAlign: 'center', padding: '1rem' }}>No documents registered.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Main Tabbed Explorer */}
      <div className="glass-card" style={{ padding: '2rem' }}>
        <div className="tabs-nav">
          <button
            className={`tab-btn ${activeTab === 'orgs' ? 'active' : ''}`}
            onClick={() => setActiveTab('orgs')}
          >
            Organizations
          </button>
          <button
            className={`tab-btn ${activeTab === 'docs' ? 'active' : ''}`}
            onClick={() => setActiveTab('docs')}
          >
            Managed Documents
          </button>
          <button
            className={`tab-btn ${activeTab === 'escalations' ? 'active' : ''}`}
            onClick={() => setActiveTab('escalations')}
          >
            Escalations
          </button>
        </div>

        {tabLoading && (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '2rem' }}>
            <div className="spinner" />
          </div>
        )}

        {!tabLoading && activeTab === 'orgs' && (
          <div className="table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Organization Name</th>
                  <th>Workers</th>
                  <th>Documents</th>
                  <th>Work Logs</th>
                  <th>Convs</th>
                  <th>Active Sessions</th>
                  <th>Created At</th>
                </tr>
              </thead>
              <tbody>
                {organizations.map((org) => (
                  <tr key={org.id}>
                    <td style={{ fontWeight: 'bold' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <Building2 size={16} style={{ color: 'var(--brown-500)' }} />
                        {org.name}
                      </div>
                    </td>
                    <td>{org.member_count}</td>
                    <td>{org.document_count}</td>
                    <td>{org.work_log_count}</td>
                    <td>{org.conversation_count}</td>
                    <td>
                      {org.active_session_count > 0 ? (
                        <span className="badge badge-success">{org.active_session_count} Active</span>
                      ) : (
                        <span className="badge badge-info">None</span>
                      )}
                    </td>
                    <td>{formatDate(org.created_at)}</td>
                  </tr>
                ))}
                {organizations.length === 0 && (
                  <tr>
                    <td colSpan={7} style={{ textAlign: 'center', color: 'var(--brown-400)', padding: '2rem' }}>
                      No organizations found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {!tabLoading && activeTab === 'docs' && (
          <div>
            {/* Filters Row */}
            <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: '200px' }}>
                <label className="form-label">Filter by Organization</label>
                <select
                  className="form-select"
                  value={docOrgFilter}
                  onChange={(e) => setDocOrgFilter(e.target.value)}
                >
                  <option value="">All Organizations</option>
                  {organizations.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.name}
                    </option>
                  ))}
                </select>
              </div>
              <div style={{ flex: 1, minWidth: '200px' }}>
                <label className="form-label">Filter by Status</label>
                <select
                  className="form-select"
                  value={docStatusFilter}
                  onChange={(e) => setDocStatusFilter(e.target.value)}
                >
                  <option value="">All Statuses</option>
                  <option value="processed">Processed</option>
                  <option value="processing">Processing</option>
                  <option value="failed">Failed</option>
                  <option value="generated">Generated</option>
                </select>
              </div>
            </div>

            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Display Name</th>
                    <th>Kind</th>
                    <th>Source</th>
                    <th>Size</th>
                    <th>Status</th>
                    <th>Updated At</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((doc) => (
                    <tr key={doc.id}>
                      <td>
                        <div style={{ display: 'flex', flexDirection: 'column' }}>
                          <span style={{ fontWeight: 'bold' }}>{doc.display_name}</span>
                          <span style={{ fontSize: '0.75rem', color: 'var(--brown-500)', fontFamily: 'var(--font-mono)' }}>
                            {doc.filename}
                          </span>
                        </div>
                      </td>
                      <td>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{doc.document_kind}</span>
                      </td>
                      <td>{doc.source_type}</td>
                      <td>{formatBytes(doc.size_bytes)}</td>
                      <td>{getStatusBadge(doc.status)}</td>
                      <td>{formatDate(doc.updated_at)}</td>
                      <td>
                        <button className="btn btn-secondary btn-small" onClick={() => setSelectedDoc(doc)}>
                          <Eye size={12} />
                          Details
                        </button>
                      </td>
                    </tr>
                  ))}
                  {documents.length === 0 && (
                    <tr>
                      <td colSpan={7} style={{ textAlign: 'center', color: 'var(--brown-400)', padding: '2rem' }}>
                        No documents matching filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {!tabLoading && activeTab === 'escalations' && (
          <div>
            {/* Filters Row */}
            <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', maxWidth: '300px' }}>
              <div style={{ width: '100%' }}>
                <label className="form-label">Filter by Status</label>
                <select
                  className="form-select"
                  value={escStatusFilter}
                  onChange={(e) => setEscStatusFilter(e.target.value)}
                >
                  <option value="">All Escalations</option>
                  <option value="pending">Pending</option>
                  <option value="failed">Failed</option>
                  <option value="resolved">Resolved</option>
                </select>
              </div>
            </div>

            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Reporter / Organization</th>
                    <th>Channel</th>
                    <th>Report Text Summary</th>
                    <th>Destination</th>
                    <th>Status</th>
                    <th>Reported At</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {escalations.map((esc) => (
                    <tr key={esc.id}>
                      <td>
                        <div style={{ display: 'flex', flexDirection: 'column' }}>
                          <span style={{ fontWeight: 'bold' }}>{esc.user_name || 'System'}</span>
                          <span style={{ fontSize: '0.75rem', color: 'var(--brown-500)' }}>
                            {esc.organization_name || 'No Org'}
                          </span>
                        </div>
                      </td>
                      <td>
                        <span style={{ textTransform: 'uppercase', fontSize: '0.8rem', fontWeight: 600 }}>{esc.platform || 'N/A'}</span>
                      </td>
                      <td style={{ maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {esc.report_text}
                      </td>
                      <td>{esc.destination || '—'}</td>
                      <td>{getStatusBadge(esc.status)}</td>
                      <td>{formatDate(esc.created_at)}</td>
                      <td>
                        <button className="btn btn-secondary btn-small" onClick={() => setSelectedEsc(esc)}>
                          <Eye size={12} />
                          Review
                        </button>
                      </td>
                    </tr>
                  ))}
                  {escalations.length === 0 && (
                    <tr>
                      <td colSpan={7} style={{ textAlign: 'center', color: 'var(--brown-400)', padding: '2rem' }}>
                        No escalations found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Document Detail Modal */}
      {selectedDoc && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(43, 30, 22, 0.4)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1.5rem' }}>
          <div className="glass-card fade-in" style={{ width: '100%', maxWidth: '600px', maxHeight: '90vh', overflowY: 'auto', background: 'var(--bg-milk)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.5rem' }}>
              <div>
                <h2>{selectedDoc.display_name}</h2>
                <span className="badge badge-info" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>{selectedDoc.filename}</span>
              </div>
              <button 
                className="btn btn-secondary btn-small"
                onClick={() => setSelectedDoc(null)}
              >
                Close
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', fontSize: '0.9rem' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', padding: '1rem', background: 'var(--bg-cream)', borderRadius: '8px' }}>
                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--brown-500)', display: 'block' }}>Document Kind</span>
                  <strong>{selectedDoc.document_kind}</strong>
                </div>
                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--brown-500)', display: 'block' }}>Pipeline Status</span>
                  {getStatusBadge(selectedDoc.status)}
                </div>
                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--brown-500)', display: 'block' }}>Source Type</span>
                  <strong>{selectedDoc.source_type}</strong>
                </div>
                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--brown-500)', display: 'block' }}>File Size</span>
                  <strong>{formatBytes(selectedDoc.size_bytes)}</strong>
                </div>
                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--brown-500)', display: 'block' }}>Owner</span>
                  <strong>{selectedDoc.owner_name || 'System Bot'}</strong>
                </div>
                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--brown-500)', display: 'block' }}>Updates Registry</span>
                  <strong>{selectedDoc.update_count} modifications</strong>
                </div>
              </div>

              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--brown-500)', display: 'block', marginBottom: '0.25rem' }}>Pipeline summary</span>
                <div style={{ padding: '1rem', background: 'white', border: '1px solid var(--brown-100)', borderRadius: '8px', color: 'var(--brown-800)', minHeight: '60px' }}>
                  {selectedDoc.summary || <span style={{ color: 'var(--brown-400)', fontStyle: 'italic' }}>No index summary available for this file.</span>}
                </div>
              </div>

              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--brown-500)', display: 'block', marginBottom: '0.25rem' }}>RAG Metadata Tags</span>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  {selectedDoc.tags.map((tag) => (
                    <span key={tag} className="badge badge-info" style={{ textTransform: 'none', background: 'var(--bg-cream-dark)', color: 'var(--brown-800)', borderColor: 'var(--brown-200)' }}>
                      #{tag}
                    </span>
                  ))}
                  {selectedDoc.tags.length === 0 && <span style={{ color: 'var(--brown-400)', fontSize: '0.85rem' }}>No index tags.</span>}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Escalation Detail Modal */}
      {selectedEsc && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(43, 30, 22, 0.4)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1.5rem' }}>
          <div className="glass-card fade-in" style={{ width: '100%', maxWidth: '650px', maxHeight: '90vh', overflowY: 'auto', background: 'var(--bg-milk)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.5rem' }}>
              <div>
                <h2>Developer Escalation Review</h2>
                <span style={{ fontSize: '0.75rem', color: 'var(--brown-500)' }}>ID: {selectedEsc.id}</span>
              </div>
              <button 
                className="btn btn-secondary btn-small"
                onClick={() => setSelectedEsc(null)}
              >
                Close
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', fontSize: '0.9rem' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', padding: '1rem', background: 'var(--bg-cream)', borderRadius: '8px' }}>
                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--brown-500)', display: 'block' }}>Reporter Username</span>
                  <strong>{selectedEsc.user_name || 'System Bot'}</strong>
                </div>
                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--brown-500)', display: 'block' }}>Escalation Status</span>
                  {getStatusBadge(selectedEsc.status)}
                </div>
                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--brown-500)', display: 'block' }}>Source Channel</span>
                  <strong style={{ textTransform: 'uppercase' }}>{selectedEsc.platform || 'System'}</strong>
                </div>
                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--brown-500)', display: 'block' }}>Dispatch Target</span>
                  <strong>{selectedEsc.destination || 'None'}</strong>
                </div>
                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--brown-500)', display: 'block' }}>Created Timestamp</span>
                  <strong>{formatDate(selectedEsc.created_at)}</strong>
                </div>
                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--brown-500)', display: 'block' }}>Dispatched Timestamp</span>
                  <strong>{formatDate(selectedEsc.sent_at)}</strong>
                </div>
              </div>

              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--brown-500)', display: 'block', marginBottom: '0.25rem' }}>Report Details</span>
                <div style={{ padding: '1rem', background: 'white', border: '1px solid var(--brown-100)', borderRadius: '8px', color: 'var(--brown-800)', lineHeight: '1.6' }}>
                  {selectedEsc.report_text}
                </div>
              </div>

              {selectedEsc.error_text && (
                <div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--brown-500)', display: 'block', marginBottom: '0.25rem' }}>System Stack Trace / Error Payload</span>
                  <pre style={{ padding: '1rem', background: '#2B1E16', color: '#F8F3EE', borderRadius: '8px', fontSize: '0.8rem', fontFamily: 'var(--font-mono)', overflowX: 'auto', whiteSpace: 'pre-wrap' }}>
                    {selectedEsc.error_text}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
