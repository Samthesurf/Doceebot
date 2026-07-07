/* oxlint-disable react-hooks/exhaustive-deps */
import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { getLogs } from '../api';
import type { ConversationLogRow } from '../types';
import {
  KeyRound,
  User,
  Settings,
  MessageSquare,
  Building2,
  ChevronDown,
  ChevronUp,
  Search,
} from 'lucide-react';

export const LogsView: React.FC = () => {
  const { token, demoMode } = useAuth();
  const [searchParams] = useSearchParams();

  // Target session passed from Search (e.g. /logs?session=...&turn=...)
  const targetSessionId = searchParams.get('session');
  const cameFromSearch = Boolean(targetSessionId);

  // Auth state for logs password
  const [password, setPassword] = useState('');
  const [isAuthorized, setIsAuthorized] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [authLoading, setAuthLoading] = useState(false);

  // Logs state
  const [conversations, setConversations] = useState<ConversationLogRow[]>([]);
  const [selectedSession, setSelectedSession] = useState<ConversationLogRow | null>(null);
  const [targetMissing, setTargetMissing] = useState(false);

  // Details accordion state
  const [openMetadataIndex, setOpenMetadataIndex] = useState<number | null>(null);

  // Restore password if cached
  // oxlint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const cachedPassword = sessionStorage.getItem('doceebot_logs_pwd');
    if (cachedPassword) {
      handleAuthAttempt(cachedPassword);
    }
  }, []);

  const handleAuthAttempt = async (pwdToTest: string) => {
    setAuthLoading(true);
    setAuthError(null);
    try {
      const res = await getLogs(token, pwdToTest);
      setConversations(res.conversations);
      setIsAuthorized(true);
      sessionStorage.setItem('doceebot_logs_pwd', pwdToTest);
      setPassword(pwdToTest);

      if (targetSessionId) {
        const match = res.conversations.find(
          (c: ConversationLogRow) => c.conversation_id === targetSessionId
        );
        if (match) {
          setSelectedSession(match);
          setTargetMissing(false);
        } else {
          // Gracefully fall back: keep first conversation selected if any.
          setSelectedSession(res.conversations[0] ?? null);
          setTargetMissing(true);
        }
      } else if (res.conversations.length > 0) {
        setSelectedSession(res.conversations[0]);
      }
    } catch (err: any) {
      console.error(err);
      setAuthError(err.message || 'Failed to authenticate logs pipeline.');
      setIsAuthorized(false);
      sessionStorage.removeItem('doceebot_logs_pwd');
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLoginSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!password.trim()) return;
    handleAuthAttempt(password);
  };

  const handleLogRefresh = async () => {
    try {
      const res = await getLogs(token, password);
      setConversations(res.conversations);
      if (selectedSession) {
        const updated = res.conversations.find((c: ConversationLogRow) => c.conversation_id === selectedSession.conversation_id);
        if (updated) setSelectedSession(updated);
      }
      if (targetSessionId) {
        const match = res.conversations.find((c: ConversationLogRow) => c.conversation_id === targetSessionId);
        if (match) {
          setSelectedSession(match);
          setTargetMissing(false);
        } else {
          setTargetMissing(true);
        }
      }
    } catch (err) {
      console.error('Failed to refresh logs:', err);
    }
  };

  const handleSessionSelect = (session: ConversationLogRow) => {
    setSelectedSession(session);
    setOpenMetadataIndex(null);
  };

  const toggleMetadata = (idx: number) => {
    setOpenMetadataIndex(openMetadataIndex === idx ? null : idx);
  };

  const getPlatformIcon = (platform: string | null) => {
    if (!platform) return '💬';
    switch (platform.toLowerCase()) {
      case 'whatsapp':
        return <span style={{ color: '#25D366', fontWeight: 'bold' }}>WA</span>;
      case 'telegram':
        return <span style={{ color: '#0088cc', fontWeight: 'bold' }}>TG</span>;
      default:
        return '💬';
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '—';
    return new Date(dateStr).toLocaleString(undefined, {
      dateStyle: 'short',
      timeStyle: 'short',
    });
  };

  // 1. Password input screen
  if (!isAuthorized) {
    return (
      <div className="glass-card password-screen fade-in">
        <div className="login-icon" style={{ background: 'var(--status-warning-bg)', color: 'var(--accent-gold)' }}>
          <KeyRound size={32} />
        </div>
        <h2>Conversation Logs Authorization</h2>
        <p style={{ marginBottom: '1.5rem' }}>
          Viewing conversation logs and audit trails requires the secure system password. This route exposes unredacted user message traces.
        </p>

        {authError && (
          <div className="badge badge-error" style={{ display: 'block', margin: '0 auto 1.25rem', width: 'fit-content' }}>
            {authError}
          </div>
        )}

        <form onSubmit={handleLoginSubmit}>
          <div className="form-group" style={{ textAlign: 'left' }}>
            <label className="form-label">System Logs Password</label>
            <input
              type="password"
              className="form-input"
              placeholder="Enter password..."
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={authLoading}
              autoFocus
            />
          </div>

          <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={authLoading}>
            {authLoading ? <div className="spinner" style={{ width: '18px', height: '18px' }} /> : 'Unlock Logs Pipeline'}
          </button>
        </form>

        {demoMode && (
          <div 
            style={{ 
              marginTop: '1.5rem', 
              fontSize: '0.8rem', 
              color: 'var(--brown-500)',
              padding: '0.5rem',
              background: 'var(--bg-cream)',
              borderRadius: '6px'
            }}
          >
            💡 Hint: Enter <strong>demo</strong> in Demo Mode to gain access.
          </div>
        )}
      </div>
    );
  }

  // 2. Main logs list and detail layout
  return (
    <div className="fade-in">
      <div className="section-header" style={{ marginBottom: '1.5rem' }}>
        <div>
          <h1>Conversation Logs &amp; Audit Trail</h1>
          <p>Auditing raw inbound webhooks, intent classification metrics, and responses.</p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button className="btn btn-secondary" onClick={handleLogRefresh}>
            Refresh Logs
          </button>
          <button 
            className="btn btn-danger btn-outline"
            onClick={() => {
              setIsAuthorized(false);
              sessionStorage.removeItem('doceebot_logs_pwd');
              setPassword('');
            }}
          >
            Lock Terminal
          </button>
        </div>
      </div>

      {cameFromSearch && targetMissing && (
        <div className="glass-card" style={{ borderLeft: '4px solid var(--status-error-text)', background: 'var(--status-error-bg)', marginBottom: '1.5rem', padding: '1rem 1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Search size={18} style={{ color: 'var(--status-error-text)' }} />
            <p style={{ color: 'var(--status-error-text)', fontWeight: 700, margin: 0 }}>Session not found</p>
          </div>
          <p style={{ color: 'var(--status-error-text)', marginTop: '0.4rem', marginBottom: 0 }}>
            The conversation from your Search result is no longer available in the logs. Showing other conversations instead.
          </p>
        </div>
      )}

      {cameFromSearch && !targetMissing && (
        <div className="glass-card" style={{ borderLeft: '4px solid var(--accent-gold)', background: 'var(--accent-gold-bg)', marginBottom: '1.5rem', padding: '1rem 1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Search size={18} style={{ color: 'var(--accent-gold)' }} />
            <p style={{ color: 'var(--brown-800)', fontWeight: 700, margin: 0 }}>
              Opened from Search
            </p>
          </div>
          <p style={{ color: 'var(--brown-700)', marginTop: '0.4rem', marginBottom: 0 }}>
            Auto-selected the conversation session linked to your search result.
          </p>
        </div>
      )}

      <div className="logs-layout">
        {/* Left Side: Sessions List */}
        <div className="glass-card logs-sidebar">
          <h3>Active &amp; Closed Workspaces</h3>
          <div className="logs-list">
            {conversations.map((session) => {
              const isActive = selectedSession?.conversation_id === session.conversation_id;
              return (
                <div
                  key={session.conversation_id}
                  className={`log-session-card ${isActive ? 'active' : ''}`}
                  onClick={() => handleSessionSelect(session)}
                >
                  <div className="session-card-header">
                    <span className="session-worker-name">{session.user_name || 'Anonymous User'}</span>
                    <span className="badge badge-info" style={{ fontSize: '0.7rem', padding: '0.1rem 0.4rem' }}>
                      {getPlatformIcon(session.platform)}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--brown-600)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {session.organization_name || 'No Organization'}
                  </div>
                  <div className="session-metadata">
                    <span>Turns: {session.turn_count}</span>
                    <span>•</span>
                    <span>Logs: {session.work_log_count}</span>
                    <span>•</span>
                    <span>{formatDate(session.last_message_at)}</span>
                  </div>
                </div>
              );
            })}
            {conversations.length === 0 && (
              <div className="empty-state" style={{ height: 'auto', padding: '2rem' }}>
                <p>No logged conversations available.</p>
              </div>
            )}
          </div>
        </div>

        {/* Right Side: Conversation Turns View */}
        <div className="turns-viewer">
          {selectedSession ? (
            <>
              {/* Turn Viewer Header */}
              <div className="turns-viewer-header">
                <div className="turns-viewer-meta">
                  <div>
                    <h2 style={{ marginBottom: '0.25rem' }}>{selectedSession.user_name || 'Worker Audit'}</h2>
                    <p style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}>
                      <Building2 size={14} />
                      {selectedSession.organization_name || 'Not mapped to organization'}
                    </p>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <span className={`badge ${selectedSession.status === 'active' ? 'badge-success' : 'badge-info'}`} style={{ marginBottom: '0.25rem' }}>
                      Session Status: {selectedSession.status || 'unknown'}
                    </span>
                    <div style={{ fontSize: '0.75rem', color: 'var(--brown-500)', fontFamily: 'var(--font-mono)' }}>
                      UUID: {selectedSession.conversation_id}
                    </div>
                  </div>
                </div>
                
                <div className="summary-strip-shell">
                  <div className="summary-strip">
                    <div className="summary-card">
                      <span className="summary-card-label">Conversation Turns</span>
                      <strong className="summary-card-value">{selectedSession.turn_count}</strong>
                    </div>
                    <div className="summary-card">
                      <span className="summary-card-label">Work Logs</span>
                      <strong className="summary-card-value">{selectedSession.work_log_count}</strong>
                    </div>
                    <div className="summary-card">
                      <span className="summary-card-label">Escalations</span>
                      <strong className="summary-card-value">{selectedSession.escalation_count}</strong>
                    </div>
                    <div className="summary-card">
                      <span className="summary-card-label">Started</span>
                      <strong className="summary-card-value summary-card-value-date">{formatDate(selectedSession.started_at)}</strong>
                    </div>
                  </div>
                </div>
                <div className="summary-scroll-hint">Swipe for more stats →</div>
              </div>

              {/* Turns List Bubble Stream */}
              <div className="turns-list">
                {selectedSession.turns.map((turn, idx) => {
                  const isInbound = turn.direction === 'inbound';
                  const isMetadataOpen = openMetadataIndex === idx;
                  
                  return (
                    <div key={idx} className={`turn-item ${isInbound ? 'inbound' : 'outbound'}`}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.75rem', color: 'var(--brown-500)', marginBottom: '0.2rem', alignSelf: isInbound ? 'flex-start' : 'flex-end' }}>
                        {isInbound ? <User size={12} /> : <Settings size={12} />}
                        <span>{isInbound ? 'Inbound Payload' : 'Agent Response'}</span>
                      </div>
                      
                      <div className="turn-bubble">
                        <div>{turn.body_text}</div>
                        
                        {/* Accordion trigger for metadata */}
                        <div 
                          onClick={() => toggleMetadata(idx)}
                          style={{ 
                            marginTop: '0.5rem', 
                            paddingTop: '0.5rem', 
                            borderTop: `1px solid ${isInbound ? 'var(--brown-200)' : 'rgba(255,255,255,0.2)'}`,
                            display: 'flex', 
                            alignItems: 'center', 
                            justifyContent: 'space-between',
                            fontSize: '0.7rem',
                            cursor: 'pointer',
                            color: isInbound ? 'var(--brown-600)' : 'var(--brown-100)'
                          }}
                        >
                          <span>{isInbound ? 'Inbound Metadata Auditing' : 'LLM Processing Trace'}</span>
                          {isMetadataOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                        </div>

                        {/* Collapsible Metadata Content */}
                        {isMetadataOpen && (
                          <div 
                            className="fade-in"
                            style={{ 
                              marginTop: '0.5rem', 
                              padding: '0.5rem', 
                              background: isInbound ? 'rgba(43, 30, 22, 0.03)' : 'rgba(0,0,0,0.15)',
                              borderRadius: '4px',
                              fontFamily: 'var(--font-mono)',
                              fontSize: '0.72rem',
                              color: isInbound ? 'var(--brown-800)' : '#F8F3EE',
                              whiteSpace: 'pre-wrap',
                              wordBreak: 'break-all'
                            }}
                          >
                            {JSON.stringify(turn.metadata, null, 2)}
                          </div>
                        )}
                      </div>
                      <span className="turn-time">{formatDate(turn.occurred_at)}</span>
                    </div>
                  );
                })}

                {selectedSession.turns.length === 0 && (
                  <div className="empty-state">
                    <p>No turns recorded in this session workspace.</p>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="empty-state">
              <MessageSquare size={48} className="empty-state-icon" />
              <h3>Select a Conversation Session</h3>
              <p>Select a worker session from the list on the left to inspect raw webhook turns, audio transcripts, and intent classification audits.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
