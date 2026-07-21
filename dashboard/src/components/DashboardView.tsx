/* oxlint-disable react-hooks/exhaustive-deps */
import React, { useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import Select from './Select';
import {
  getOverview,
  getOrganizations,
  getDocuments,
  getEscalations,
  getAdminAccess,
  getAdminUsers,
  addAdminUser,
  linkAdminEmail,
} from '../api';
import type {
  OverviewResponse,
  OrganizationDashboardRow,
  DocumentDashboardRow,
  EscalationDashboardRow,
  AdminAccessResponse,
  OrgMember,
} from '../types';
import {
  Building2,
  RefreshCw,
  Sparkles,
  Eye,
  Users,
  UserPlus,
  CheckCircle2,
  AlertTriangle,
  Mail,
  Link2,
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

  // Admin Management States
  const [adminAccess, setAdminAccess] = useState<AdminAccessResponse | null>(null);
  const [adminAccessLoading, setAdminAccessLoading] = useState(false);
  const [adminAccessError, setAdminAccessError] = useState<string | null>(null);
  const [selectedOrgId, setSelectedOrgId] = useState<string>('');
  
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);
  const [membersError, setMembersError] = useState<string | null>(null);

  // Form states
  const [formOrgId, setFormOrgId] = useState<string>('');
  const [formPlatform, setFormPlatform] = useState<'whatsapp' | 'telegram'>('whatsapp');
  const [formIdentifier, setFormIdentifier] = useState<string>('');
  const [formRole, setFormRole] = useState<'worker' | 'supervisor' | 'manager' | 'org_admin'>('worker');
  const [formDisplayName, setFormDisplayName] = useState<string>('');
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  // Admin Email Linking States
  const [linkOrgId, setLinkOrgId] = useState<string>('');
  const [linkEmail, setLinkEmail] = useState<string>('');
  const [linkPlatform, setLinkPlatform] = useState<'whatsapp' | 'telegram'>('whatsapp');
  const [linkIdentifier, setLinkIdentifier] = useState<string>('');
  const [linkRole, setLinkRole] = useState<'worker' | 'supervisor' | 'manager' | 'org_admin'>('org_admin');
  const [linkDisplayName, setLinkDisplayName] = useState<string>('');
  const [linkSubmitting, setLinkSubmitting] = useState(false);
  const [linkSuccess, setLinkSuccess] = useState<string | null>(null);
  const [linkError, setLinkError] = useState<string | null>(null);

  const fetchMembers = async (orgId: string) => {
    setMembersLoading(true);
    setMembersError(null);
    try {
      const res = await getAdminUsers(token, orgId);
      setMembers(res.members);
    } catch (err: any) {
      console.error(err);
      setMembersError(err.message || 'Failed to load organization members.');
    } finally {
      setMembersLoading(false);
    }
  };

  const handleRefreshMembers = (orgId: string) => {
    if (orgId) {
      fetchMembers(orgId);
    }
  };

  const handleFormSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formOrgId || !formIdentifier.trim()) {
      setFormError('Organization and platform identifier are required.');
      return;
    }
    
    setFormSubmitting(true);
    setFormSuccess(null);
    setFormError(null);
    
    try {
      const payload = {
        org_id: formOrgId,
        platform: formPlatform,
        identifier: formIdentifier.trim(),
        role: formRole,
        display_name: formDisplayName.trim() || undefined,
      };
      
      const res = await addAdminUser(token, payload);
      
      let detailMsg = '';
      if (res.created_user && res.created_membership) {
        detailMsg = 'A new user was created and added to the organization.';
      } else if (!res.created_user && res.created_membership) {
        detailMsg = 'An existing user was added to the organization.';
      } else if (!res.created_user && !res.created_membership) {
        if (res.updated_membership_role) {
          detailMsg = `Membership role was updated to "${res.user.role}".`;
        } else {
          detailMsg = 'Membership is already active with the requested role.';
        }
      }
      
      const nameText = res.user.display_name || payload.identifier;
      setFormSuccess(`Successfully registered/updated ${nameText}! ${detailMsg}`);
      setFormIdentifier('');
      setFormDisplayName('');
      
      // Refresh member list if the updated org is the currently selected org
      if (formOrgId === selectedOrgId) {
        fetchMembers(formOrgId);
      }
      
      // Refresh general organization stats
      const orgsRes = await getOrganizations(token);
      setOrganizations(orgsRes.organizations);
    } catch (err: any) {
      console.error(err);
      if (err.status === 403) {
        setFormError('Access Forbidden (403): You do not have permission to manage users for this organization.');
      } else if (err.status === 409) {
        setFormError('Conflict Detected (409): A conflicting user membership or identifier constraint already exists in this organization.');
      } else {
        setFormError(err.message || 'An unexpected error occurred while saving the member.');
      }
    } finally {
      setFormSubmitting(false);
    }
  };

  const handleLinkEmailSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!linkOrgId || !linkEmail.trim() || !linkIdentifier.trim()) {
      setLinkError('Organization, dashboard login email, and bot user identifier are required.');
      return;
    }

    setLinkSubmitting(true);
    setLinkSuccess(null);
    setLinkError(null);

    try {
      const payload = {
        org_id: linkOrgId,
        email: linkEmail.trim(),
        platform: linkPlatform,
        identifier: linkIdentifier.trim(),
        role: linkRole,
        display_name: linkDisplayName.trim() || undefined,
      };

      const res = await linkAdminEmail(token, payload);
      const nameText = res.user.display_name || payload.identifier;
      let detail = '';
      if (res.created_user) {
        detail += 'A new bot user record was created for them. ';
      }
      if (res.created_membership) {
        detail += `They were added to ${res.organization_name} as ${formatRoleLabel(res.user.role)}. `;
      } else if (res.updated_membership_role) {
        detail += `Their role in ${res.organization_name} was set to ${formatRoleLabel(res.user.role)}. `;
      }
      if (res.email_previously_set) {
        detail += 'Their dashboard email was already linked.';
      } else {
        detail += `Their dashboard email (${res.email}) is now linked.`;
      }
      const canManage = res.user.role === 'org_admin' || res.user.role === 'manager' || res.user.role === 'supervisor';
      setLinkSuccess(
        `Linked ${nameText}! ${detail} They can now sign in to the dashboard with that email${canManage ? ' and manage this organization' : ''}.`
      );
      setLinkEmail('');
      setLinkIdentifier('');
      setLinkDisplayName('');

      if (linkOrgId === selectedOrgId) {
        fetchMembers(linkOrgId);
      }
      const orgsRes = await getOrganizations(token);
      setOrganizations(orgsRes.organizations);
    } catch (err: any) {
      console.error(err);
      if (err.status === 403) {
        setLinkError('Access Forbidden (403): You do not have permission to manage admins for this organization.');
      } else if (err.status === 409) {
        setLinkError('Conflict Detected (409): That email or identifier is already linked to a different user or organization.');
      } else if (err.status === 422) {
        setLinkError('Invalid Input (422): A valid dashboard login email is required.');
      } else {
        setLinkError(err.message || 'An unexpected error occurred while linking the email.');
      }
    } finally {
      setLinkSubmitting(false);
    }
  };

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
        setAdminAccessLoading(true);
        setAdminAccessError(null);
        
        const [resOrgs, resAdmin] = await Promise.all([
          getOrganizations(token),
          getAdminAccess(token)
        ]);
        
        setOrganizations(resOrgs.organizations);
        setAdminAccess(resAdmin);
        
        // Auto-select the first manageable organization if none is selected
        if (resAdmin.organizations.length > 0 && !selectedOrgId) {
          const firstOrgId = resAdmin.organizations[0].id;
          setSelectedOrgId(firstOrgId);
          setFormOrgId(firstOrgId);
          fetchMembers(firstOrgId);
        }
        setAdminAccessLoading(false);
      } else if (activeTab === 'docs') {
        const res = await getDocuments(token, docOrgFilter || undefined, docStatusFilter || undefined);
        setDocuments(res.documents);
      } else if (activeTab === 'escalations') {
        const res = await getEscalations(token, escStatusFilter || undefined);
        setEscalations(res.escalations);
      }
    } catch (err: any) {
      console.error(err);
      if (activeTab === 'orgs') {
        setAdminAccessError(err.message || 'Failed to load manageable organizations.');
        setAdminAccessLoading(false);
      }
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
    if (selectedOrgId) {
      fetchMembers(selectedOrgId);
    }
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

  const formatRoleLabel = (role: string) => role
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');

  const getRoleBadgeClass = (role: string) => {
    switch (role) {
      case 'org_admin':
        return 'badge-success';
      case 'supervisor':
        return 'badge-warning';
      default:
        return 'badge-info';
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
      <div className="glass-card main-explorer-card">
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
          <>
            <div className="table-wrapper" style={{ marginBottom: '2.5rem' }}>
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

            {/* Member & Access Administration Section */}
            <div className="member-admin-section">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
                <div>
                  <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                    <Users size={22} style={{ color: 'var(--brown-700)' }} />
                    Member &amp; Access Administration
                  </h2>
                  <p>Manage worker memberships, platform identifiers, and authorization roles.</p>
                </div>
                {selectedOrgId && (
                  <button 
                    className="btn btn-secondary btn-small"
                    onClick={() => handleRefreshMembers(selectedOrgId)}
                    disabled={membersLoading}
                  >
                    <RefreshCw size={12} className={membersLoading ? 'spin' : ''} />
                    Refresh Members
                  </button>
                )}
              </div>

              {adminAccessLoading ? (
                <div style={{ display: 'flex', justifyContent: 'center', padding: '2rem' }}>
                  <div className="spinner" />
                </div>
              ) : adminAccessError ? (
                <div className="badge badge-error" style={{ width: '100%', padding: '1rem', display: 'block', textAlign: 'left', borderRadius: '8px' }}>
                  <strong>Failed to load manageable organizations:</strong> {adminAccessError}
                </div>
              ) : (
                <div className="dashboard-row member-admin-row">
                  {/* Left Column: Org Selector & Existing Members List */}
                  <div className="glass-card member-admin-card">
                    <div>
                      <label className="form-label" htmlFor="admin-org-select">Manage Organization</label>
                      <Select
                        value={selectedOrgId}
                        onChange={(orgId) => {
                          setSelectedOrgId(orgId);
                          setFormOrgId(orgId);
                          if (orgId) {
                            fetchMembers(orgId);
                          } else {
                            setMembers([]);
                          }
                          setFormSuccess(null);
                          setFormError(null);
                        }}
                        options={[
                          ...(adminAccess?.organizations ?? []).map((org) => ({
                            value: org.id,
                            label: `${org.name} (${formatRoleLabel(org.role)})`,
                          })),
                        ]}
                        placeholder="-- Select an Organization --"
                      />
                    </div>

                    {selectedOrgId ? (
                      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                        <h4 style={{ marginBottom: '0.75rem', fontSize: '1rem', color: 'var(--brown-800)' }}>
                          Existing Members
                        </h4>
                        {membersLoading ? (
                          <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem', flex: 1, alignItems: 'center' }}>
                            <div className="spinner" />
                          </div>
                        ) : membersError ? (
                          <div className="badge badge-error" style={{ padding: '1rem', borderRadius: '8px' }}>
                            {membersError}
                          </div>
                        ) : (
                          <>
                            <div className="table-wrapper member-table-wrapper member-table-desktop">
                              <table className="data-table" style={{ fontSize: '0.85rem' }}>
                                <thead>
                                  <tr>
                                    <th>Name</th>
                                    <th>Identifier</th>
                                    <th>Role</th>
                                    <th>Joined</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {members.map((member) => (
                                    <tr key={member.user_id}>
                                      <td style={{ fontWeight: 'bold' }}>{member.display_name || 'Unnamed'}</td>
                                      <td>
                                        {member.phone_number ? (
                                          <div style={{ display: 'flex', flexDirection: 'column' }}>
                                            <span style={{ fontSize: '0.7rem', color: 'var(--brown-400)', textTransform: 'uppercase', fontWeight: 600 }}>WhatsApp</span>
                                            <span>{member.phone_number}</span>
                                          </div>
                                        ) : member.telegram_user_id ? (
                                          <div style={{ display: 'flex', flexDirection: 'column' }}>
                                            <span style={{ fontSize: '0.7rem', color: 'var(--brown-400)', textTransform: 'uppercase', fontWeight: 600 }}>Telegram</span>
                                            <span>@{member.telegram_user_id}</span>
                                          </div>
                                        ) : (
                                          <span style={{ color: 'var(--brown-300)' }}>No identifier</span>
                                        )}
                                      </td>
                                      <td>
                                        <span className={`badge ${getRoleBadgeClass(member.role)}`} style={{ fontSize: '0.75rem' }}>
                                          {formatRoleLabel(member.role)}
                                        </span>
                                      </td>
                                      <td>{formatDate(member.created_at)}</td>
                                    </tr>
                                  ))}
                                  {members.length === 0 && (
                                    <tr>
                                      <td colSpan={4} style={{ textAlign: 'center', color: 'var(--brown-400)', padding: '2rem' }}>
                                        No members found in this organization.
                                      </td>
                                    </tr>
                                  )}
                                </tbody>
                              </table>
                            </div>

                            <div className="member-mobile-list">
                              {members.map((member) => (
                                <article key={`${member.user_id}-mobile`} className="member-mobile-card">
                                  <div className="member-mobile-card-header">
                                    <div>
                                      <div className="member-mobile-name">{member.display_name || 'Unnamed'}</div>
                                      <div className="member-mobile-meta-label">Member Identifier</div>
                                    </div>
                                    <span className={`badge ${getRoleBadgeClass(member.role)}`} style={{ fontSize: '0.75rem' }}>
                                      {formatRoleLabel(member.role)}
                                    </span>
                                  </div>

                                  <div className="member-mobile-detail">
                                    {member.phone_number ? (
                                      <>
                                        <span className="member-mobile-meta-label">WhatsApp</span>
                                        <span>{member.phone_number}</span>
                                      </>
                                    ) : member.telegram_user_id ? (
                                      <>
                                        <span className="member-mobile-meta-label">Telegram</span>
                                        <span>@{member.telegram_user_id}</span>
                                      </>
                                    ) : (
                                      <span style={{ color: 'var(--brown-300)' }}>No identifier</span>
                                    )}
                                  </div>

                                  <div className="member-mobile-detail">
                                    <span className="member-mobile-meta-label">Joined</span>
                                    <span>{formatDate(member.created_at)}</span>
                                  </div>
                                </article>
                              ))}

                              {members.length === 0 && (
                                <div className="member-mobile-empty">No members found in this organization.</div>
                              )}
                            </div>
                          </>
                        )}
                      </div>
                    ) : (
                      <div className="member-empty-state">
                        <Users size={36} style={{ marginBottom: '1rem', opacity: 0.5, color: 'var(--brown-300)' }} />
                        <p style={{ color: 'var(--brown-500)' }}>Select an organization above to view its member registry and register new users.</p>
                      </div>
                    )}
                  </div>

                  {/* Right Column: Add/Update Member Form */}
                  <div className="glass-card member-form-card">
                    <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem', fontSize: '1.15rem' }}>
                      <UserPlus size={18} style={{ color: 'var(--brown-700)' }} />
                      Add or Update Member
                    </h3>

                    {formSuccess && (
                      <div className="glass-card" style={{ 
                        borderLeft: '4px solid var(--status-success-text)', 
                        background: 'var(--status-success-bg)', 
                        color: 'var(--status-success-text)',
                        padding: '1rem',
                        marginBottom: '1.25rem',
                        fontSize: '0.85rem'
                      }}>
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem' }}>
                          <CheckCircle2 size={16} style={{ flexShrink: 0, marginTop: '0.1rem' }} />
                          <div>{formSuccess}</div>
                        </div>
                      </div>
                    )}

                    {formError && (
                      <div className="glass-card" style={{ 
                        borderLeft: '4px solid var(--status-error-text)', 
                        background: 'var(--status-error-bg)', 
                        color: 'var(--status-error-text)',
                        padding: '1rem',
                        marginBottom: '1.25rem',
                        fontSize: '0.85rem'
                      }}>
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem' }}>
                          <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: '0.1rem' }} />
                          <div>{formError}</div>
                        </div>
                      </div>
                    )}

                    <form onSubmit={handleFormSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                      <div>
                        <label className="form-label" htmlFor="form-org-id">Target Organization <span style={{ color: 'var(--status-error-text)' }}>*</span></label>
                        <Select
                          value={formOrgId}
                          onChange={(val) => {
                            setFormOrgId(val);
                            setSelectedOrgId(val);
                            if (val) { fetchMembers(val); } else { setMembers([]); }
                          }}
                          options={(adminAccess?.organizations ?? []).map((org) => ({
                            value: org.id,
                            label: org.name,
                          }))}
                          placeholder='-- Choose Organization --'
                        />
                      </div>

                      <div>
                        <label className="form-label" htmlFor="form-platform">Platform Channel <span style={{ color: 'var(--status-error-text)' }}>*</span></label>
                        <Select
                          value={formPlatform}
                          onChange={(v) => setFormPlatform(v as 'whatsapp' | 'telegram')}
                          options={[
                            { value: 'whatsapp', label: 'WhatsApp number' },
                            { value: 'telegram', label: 'Telegram user ID' },
                          ]}
                          placeholder='Select channel'
                        />
                      </div>

                      <div>
                        <label className="form-label" htmlFor="form-identifier">
                          {formPlatform === 'whatsapp' ? 'WhatsApp Phone Number' : 'Telegram User ID'} <span style={{ color: 'var(--status-error-text)' }}>*</span>
                        </label>
                        <input
                          id="form-identifier"
                          type="text"
                          className="form-input"
                          placeholder={formPlatform === 'whatsapp' ? 'e.g. +15551234567' : 'e.g. username_or_id'}
                          value={formIdentifier}
                          onChange={(e) => setFormIdentifier(e.target.value)}
                          required
                        />
                        <span style={{ fontSize: '0.75rem', color: 'var(--brown-500)', display: 'block', marginTop: '0.25rem' }}>
                          {formPlatform === 'whatsapp' ? 'Include country code, e.g. +1...' : 'Enter telegram identifier (without @).'}
                        </span>
                      </div>

                      <div>
                        <label className="form-label" htmlFor="form-role">Authorization Role <span style={{ color: 'var(--status-error-text)' }}>*</span></label>
                        <Select
                          value={formRole}
                          onChange={(v) => setFormRole(v as any)}
                          options={[
                            { value: 'worker', label: 'Worker' },
                            { value: 'supervisor', label: 'Supervisor' },
                            { value: 'manager', label: 'Manager' },
                            { value: 'org_admin', label: 'Org Admin' },
                          ]}
                          placeholder="Select role"
                        />
                      </div>

                      <div>
                        <label className="form-label" htmlFor="form-display-name">Display Name (Optional)</label>
                        <input
                          id="form-display-name"
                          type="text"
                          className="form-input"
                          placeholder="e.g. Jane Smith"
                          value={formDisplayName}
                          onChange={(e) => setFormDisplayName(e.target.value)}
                        />
                      </div>

                      <button
                        type="submit"
                        className="btn btn-primary"
                        style={{ marginTop: '0.5rem', width: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '0.5rem' }}
                        disabled={formSubmitting}
                      >
                        {formSubmitting ? (
                          <>
                            <div className="spinner" style={{ width: '16px', height: '16px', border: '2px solid white', borderTopColor: 'transparent' }} />
                            Saving Member...
                          </>
                        ) : (
                          <>
                            <UserPlus size={16} />
                            Save Member
                          </>
                        )}
                      </button>
                    </form>
                  </div>
                </div>
              )}
            </div>

            {/* Admin Email Linking Section */}
            <div className="glass-card" style={{ marginTop: '2rem' }}>
              <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem', fontSize: '1.15rem' }}>
                <Link2 size={18} style={{ color: 'var(--brown-700)' }} />
                Link Dashboard Admin Email
              </h3>
              <p style={{ marginBottom: '1.25rem' }}>
                Connect a teammate's dashboard sign-in email to their bot user record so they can log in and manage this organization.
              </p>

              {linkSuccess && (
                <div className="glass-card" style={{ borderLeft: '4px solid var(--status-success-text)', background: 'var(--status-success-bg)', color: 'var(--status-success-text)', padding: '1rem', marginBottom: '1.25rem', fontSize: '0.85rem' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem' }}>
                    <CheckCircle2 size={16} style={{ flexShrink: 0, marginTop: '0.1rem' }} />
                    <div>{linkSuccess}</div>
                  </div>
                </div>
              )}

              {linkError && (
                <div className="glass-card" style={{ borderLeft: '4px solid var(--status-error-text)', background: 'var(--status-error-bg)', color: 'var(--status-error-text)', padding: '1rem', marginBottom: '1.25rem', fontSize: '0.85rem' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem' }}>
                    <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: '0.1rem' }} />
                    <div>{linkError}</div>
                  </div>
                </div>
              )}

              <form onSubmit={handleLinkEmailSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div>
                  <label className="form-label" htmlFor="link-org-id">Target Organization <span style={{ color: 'var(--status-error-text)' }}>*</span></label>
                  <Select
                    value={linkOrgId}
                    onChange={setLinkOrgId}
                    options={(adminAccess?.organizations ?? []).map((org) => ({
                      value: org.id,
                      label: org.name,
                    }))}
                    placeholder='-- Choose Organization --'
                  />
                </div>

                <div>
                  <label className="form-label" htmlFor="link-email">Dashboard Login Email <span style={{ color: 'var(--status-error-text)' }}>*</span></label>
                  <input
                    id="link-email"
                    type="email"
                    className="form-input"
                    placeholder="teammate@company.com"
                    value={linkEmail}
                    onChange={(e) => setLinkEmail(e.target.value)}
                    required
                  />
                </div>

                <div>
                  <label className="form-label" htmlFor="link-platform">Bot User Platform <span style={{ color: 'var(--status-error-text)' }}>*</span></label>
                  <Select
                    value={linkPlatform}
                    onChange={(v) => setLinkPlatform(v as 'whatsapp' | 'telegram')}
                    options={[
                      { value: 'whatsapp', label: 'WhatsApp number' },
                      { value: 'telegram', label: 'Telegram user ID' },
                    ]}
                    placeholder='Select channel'
                  />
                </div>

                <div>
                  <label className="form-label" htmlFor="link-identifier">
                    {linkPlatform === 'whatsapp' ? 'WhatsApp Phone Number' : 'Telegram User ID'} <span style={{ color: 'var(--status-error-text)' }}>*</span>
                  </label>
                  <input
                    id="link-identifier"
                    type="text"
                    className="form-input"
                    placeholder={linkPlatform === 'whatsapp' ? 'e.g. +155****4567' : 'e.g. username_or_id'}
                    value={linkIdentifier}
                    onChange={(e) => setLinkIdentifier(e.target.value)}
                    required
                  />
                  <span style={{ fontSize: '0.75rem', color: 'var(--brown-500)', display: 'block', marginTop: '0.25rem' }}>
                    {linkPlatform === 'whatsapp'
                      ? 'Enter the same WhatsApp number this person uses with the bot.'
                      : 'Enter the same Telegram identifier this person uses with the bot.'}
                  </span>
                </div>

                <div>
                  <label className="form-label" htmlFor="link-role">Authorization Role <span style={{ color: 'var(--status-error-text)' }}>*</span></label>
                  <Select
                    value={linkRole}
                    onChange={(v) => setLinkRole(v as any)}
                    options={[
                      { value: 'org_admin', label: 'Org Admin' },
                      { value: 'manager', label: 'Manager' },
                      { value: 'supervisor', label: 'Supervisor' },
                      { value: 'worker', label: 'Worker' },
                    ]}
                    placeholder="Select role"
                  />
                </div>

                <div>
                  <label className="form-label" htmlFor="link-display-name">Display Name (Optional)</label>
                  <input
                    id="link-display-name"
                    type="text"
                    className="form-input"
                    placeholder="e.g. Jane Smith"
                    value={linkDisplayName}
                    onChange={(e) => setLinkDisplayName(e.target.value)}
                  />
                </div>

                <button
                  type="submit"
                  className="btn btn-primary"
                  style={{ marginTop: '0.5rem', width: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '0.5rem' }}
                  disabled={linkSubmitting}
                >
                  {linkSubmitting ? (
                    <>
                      <div className="spinner" style={{ width: '16px', height: '16px', border: '2px solid white', borderTopColor: 'transparent' }} />
                      Linking Email...
                    </>
                  ) : (
                    <>
                      <Mail size={16} />
                      Link Admin Email
                    </>
                  )}
                </button>
              </form>
            </div>
          </>
        )}

        {!tabLoading && activeTab === 'docs' && (
          <div>
            {/* Filters Row */}
            <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: '200px' }}>
                <label className="form-label">Filter by Organization</label>
                <Select
                  value={docOrgFilter}
                  onChange={setDocOrgFilter}
                  options={organizations.map((o) => ({ value: o.id, label: o.name }))}
                  placeholder="All Organizations"
                />
              </div>
              <div style={{ flex: 1, minWidth: '200px' }}>
                <label className="form-label">Filter by Status</label>
                <Select
                  value={docStatusFilter}
                  onChange={setDocStatusFilter}
                  options={[
                    { value: '', label: 'All Statuses' },
                    { value: 'processed', label: 'Processed' },
                    { value: 'processing', label: 'Processing' },
                    { value: 'failed', label: 'Failed' },
                    { value: 'generated', label: 'Generated' },
                  ]}
                  placeholder="All Statuses"
                />
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
                <Select
                  value={escStatusFilter}
                  onChange={setEscStatusFilter}
                  options={[
                    { value: '', label: 'All Escalations' },
                    { value: 'pending', label: 'Pending' },
                    { value: 'failed', label: 'Failed' },
                    { value: 'resolved', label: 'Resolved' },
                  ]}
                  placeholder="All Escalations"
                />
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
