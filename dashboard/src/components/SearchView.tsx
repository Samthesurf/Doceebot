import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, User, AlertTriangle, ListFilter, ClipboardList, MessageSquare, History, ArrowRight, ExternalLink } from 'lucide-react';
import { getOrganizations, searchSessions } from '../api';
import { useAuth } from '../contexts/AuthContext';
import type { OrganizationDashboardRow, SessionSearchResultRow } from '../types';

const RESULT_TYPE_ORDER = ['work_log', 'turn', 'session'] as const;
type ResultType = (typeof RESULT_TYPE_ORDER)[number];

const RESULT_TYPE_LABELS: Record<ResultType, string> = {
  work_log: 'Work Logs',
  turn: 'Message Turns',
  session: 'Sessions',
};

function escapeRegExp(input: string): string {
  return input.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Splits text into parts, highlighting case-insensitive matches of any query token.
function highlightMatched(text: string, query: string): React.ReactNode {
  const tokens = Array.from(
    new Set(
      query
        .trim()
        .split(/\s+/)
        .filter((t) => t.length > 0)
        .map(escapeRegExp)
    )
  ).sort((a, b) => b.length - a.length);

  if (tokens.length === 0) {
    return text;
  }

  const splitRegex = new RegExp(`(${tokens.join('|')})`, 'gi');
  const exactMatchRegex = new RegExp(`^(?:${tokens.join('|')})$`, 'i');
  const parts = text.split(splitRegex);

  return parts.map((part, idx) =>
    exactMatchRegex.test(part) ? (
      <mark key={idx} className="search-highlight">
        {part}
      </mark>
    ) : (
      <React.Fragment key={idx}>{part}</React.Fragment>
    )
  );
}

export const SearchView: React.FC = () => {
  const { token } = useAuth();
  const navigate = useNavigate();

  // Search form inputs
  const [query, setQuery] = useState('');
  const [orgId, setOrgId] = useState('');
  const [userId, setUserId] = useState('');
  const [limit, setLimit] = useState(10);

  // States
  const [organizations, setOrganizations] = useState<OrganizationDashboardRow[]>([]);
  const [results, setResults] = useState<SessionSearchResultRow[]>([]);
  const [loadingOrgs, setLoadingOrgs] = useState(true);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  // Load organizations
  useEffect(() => {
    const loadOrgs = async () => {
      setLoadingOrgs(true);
      try {
        const res = await getOrganizations(token);
        setOrganizations(res.organizations);
        if (res.organizations.length > 0) {
          setOrgId(res.organizations[0].id);
        }
      } catch (err) {
        console.error(err);
        setError('Failed to load organizations.');
      } finally {
        setLoadingOrgs(false);
      }
    };
    void loadOrgs();
  }, [token]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) {
      return;
    }
    if (!orgId) {
      setError('Please select an organization.');
      return;
    }

    setSearching(true);
    setError(null);
    try {
      const res = await searchSessions(token, query.trim(), orgId, userId.trim() || undefined, limit);
      setResults(res.results);
      setHasSearched(true);
    } catch (err: any) {
      console.error(err);
      setError(err.message || 'Search failed. Please verify query inputs.');
    } finally {
      setSearching(false);
    }
  };

  const getResultIcon = (type: string) => {
    switch (type) {
      case 'work_log':
        return <ClipboardList size={16} style={{ color: 'var(--accent-gold)' }} />;
      case 'turn':
        return <MessageSquare size={16} style={{ color: 'var(--brown-500)' }} />;
      case 'session':
        return <History size={16} style={{ color: 'var(--brown-700)' }} />;
      default:
        return <Search size={16} />;
    }
  };

  const getResultBadge = (type: string) => {
    switch (type) {
      case 'work_log':
        return <span className="badge badge-success">Work Log</span>;
      case 'turn':
        return <span className="badge badge-info">Message Turn</span>;
      case 'session':
        return <span className="badge badge-warning">Session</span>;
      default:
        return <span className="badge badge-info">{type}</span>;
    }
  };

  const formatDateTime = (dateStr: string | null | undefined) => {
    if (!dateStr) return '—';
    return new Date(dateStr).toLocaleString(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  };

  const formatWorkDate = (dateStr: string | null | undefined) => {
    if (!dateStr) return '—';
    return new Date(dateStr).toLocaleDateString(undefined, {
      dateStyle: 'medium',
    });
  };

  // Group results by result_type preserving API order, in the fixed order.
  const groupedResults = useMemo(() => {
    const groups: Record<ResultType, SessionSearchResultRow[]> = {
      work_log: [],
      turn: [],
      session: [],
    };
    for (const result of results) {
      if (result.result_type in groups) {
        groups[result.result_type as ResultType].push(result);
      }
    }
    return RESULT_TYPE_ORDER.map((type) => ({
      type,
      items: groups[type],
    })).filter((group) => group.items.length > 0);
  }, [results]);

  const handleOpenInLogs = (result: SessionSearchResultRow) => {
    const params = new URLSearchParams();
    params.set('session', result.session_id);
    if (result.result_type === 'turn' && result.source_id) {
      params.set('turn', result.source_id);
    }
    navigate(`/logs?${params.toString()}`);
  };

  return (
    <div className="fade-in">
      <div className="section-header">
        <div>
          <h1>Session Search</h1>
          <p>Search past sessions, work logs, and message turns across the selected organization.</p>
        </div>
      </div>

      {error && !searching && (
        <div className="glass-card" style={{ borderLeft: '4px solid var(--status-error-text)', marginBottom: '1.5rem', background: 'var(--status-error-bg)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <AlertTriangle size={18} style={{ color: 'var(--status-error-text)' }} />
            <p style={{ color: 'var(--status-error-text)', fontWeight: 700, margin: 0 }}>Search Failure</p>
          </div>
          <p style={{ color: 'var(--status-error-text)', marginTop: '0.5rem', marginBottom: 0 }}>{error}</p>
        </div>
      )}

      {/* Search Input Panel */}
      <div className="glass-card" style={{ marginBottom: '2rem' }}>
        <form onSubmit={handleSearch}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
            <div>
              <label className="form-label">Search Query</label>
              <div style={{ position: 'relative' }}>
                <input
                  type="text"
                  className="form-input"
                  style={{ paddingLeft: '2.5rem' }}
                  placeholder="e.g. tractor Plot C-2, Yoruba voice note, tomatoes..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  disabled={loadingOrgs}
                  required
                />
                <Search size={18} style={{ position: 'absolute', left: '0.85rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--brown-400)' }} />
              </div>
            </div>

            <div>
              <label className="form-label">Organization</label>
              <div style={{ position: 'relative' }}>
                <select
                  className="form-select"
                  value={orgId}
                  onChange={(e) => setOrgId(e.target.value)}
                  disabled={loadingOrgs}
                  required
                >
                  {loadingOrgs ? (
                    <option>Loading tenants...</option>
                  ) : (
                    organizations.map((org) => (
                      <option key={org.id} value={org.id}>
                        {org.name}
                      </option>
                    ))
                  )}
                </select>
              </div>
            </div>

            <div>
              <label className="form-label">Result Limit</label>
              <select
                className="form-select"
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value))}
                disabled={loadingOrgs}
              >
                <option value={5}>Top 5 results</option>
                <option value={10}>Top 10 results</option>
                <option value={20}>Top 20 results</option>
                <option value={50}>Top 50 results</option>
              </select>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', alignItems: 'end' }}>
            <div>
              <label className="form-label">Optional User ID filter (UUID)</label>
              <div style={{ position: 'relative' }}>
                <input
                  type="text"
                  className="form-input"
                  style={{ paddingLeft: '2.5rem' }}
                  placeholder="Optional exact user UUID"
                  value={userId}
                  onChange={(e) => setUserId(e.target.value)}
                  disabled={loadingOrgs}
                />
                <User size={18} style={{ position: 'absolute', left: '0.85rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--brown-400)' }} />
              </div>
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              style={{ width: '100%', height: '44px' }}
              disabled={searching || loadingOrgs || !query.trim()}
            >
              {searching ? (
                <>
                  <div className="spinner spinner-small" style={{ borderColor: 'white', borderTopColor: 'transparent', display: 'inline-block' }} />
                  Searching...
                </>
              ) : (
                <>
                  <Search size={16} />
                  Execute Search
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Results Display */}
      {searching && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '30vh', gap: '1rem' }}>
          <div className="spinner" style={{ width: '40px', height: '40px', borderWidth: '4px' }} />
          <p style={{ color: 'var(--brown-500)' }}>Scanning session indexes...</p>
        </div>
      )}

      {!searching && hasSearched && (
        <div className="fade-in">
          <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem' }}>
            <ListFilter size={18} style={{ color: 'var(--accent-gold)' }} />
            Search Results ({results.length})
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
            {groupedResults.map((group) => (
              <div key={group.type}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.6rem',
                    marginBottom: '0.9rem',
                    paddingBottom: '0.5rem',
                    borderBottom: '2px solid var(--brown-100)',
                  }}
                >
                  {getResultIcon(group.type)}
                  <h4 style={{ margin: 0, fontSize: '1rem', color: 'var(--brown-800)' }}>
                    {RESULT_TYPE_LABELS[group.type]}
                  </h4>
                  <span className="badge badge-info" style={{ fontSize: '0.7rem', padding: '0.1rem 0.45rem' }}>
                    {group.items.length}
                  </span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  {group.items.map((result, idx) => {
                    const displayScore = Math.round(result.score * 100);
                    return (
                      <div key={`${result.result_type}-${result.source_id}-${idx}`} className="glass-card" style={{ padding: '1.5rem', transition: 'var(--transition-smooth)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.75rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', padding: '0.25rem 0.5rem', background: 'var(--bg-cream)', borderRadius: '6px' }}>
                              {getResultBadge(result.result_type)}
                            </div>
                            <span className="badge badge-info" style={{ textTransform: 'none', fontFamily: 'var(--font-mono)', fontSize: '0.7rem' }}>
                              Score: {displayScore}%
                            </span>
                          </div>

                          <div style={{ fontSize: '0.8rem', color: 'var(--brown-500)' }}>
                            {result.result_type === 'work_log' && result.work_log_date ? (
                              <span>Work Date: <strong>{formatWorkDate(result.work_log_date)}</strong></span>
                            ) : (
                              <span>Started: <strong>{formatDateTime(result.session_started_at)}</strong></span>
                            )}
                          </div>
                        </div>

                        <h3 style={{ fontSize: '1.15rem', marginBottom: '0.5rem', color: 'var(--brown-900)' }}>
                          {highlightMatched(result.display_title, query)}
                        </h3>

                        <p style={{ color: 'var(--brown-800)', background: 'white', padding: '0.75rem 1rem', border: '1px solid var(--brown-100)', borderRadius: '6px', fontSize: '0.9rem', marginBottom: '0.75rem', lineHeight: '1.5' }}>
                          {highlightMatched(result.snippet, query)}
                        </p>

                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', fontSize: '0.75rem', color: 'var(--brown-500)' }}>
                          <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                            <span>Session ID: <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--brown-700)' }}>{result.session_id}</code></span>
                            {result.session_status && (
                              <span>
                                Status: <span className={`badge ${result.session_status === 'active' ? 'badge-success' : 'badge-info'}`} style={{ fontSize: '0.65rem', padding: '0.05rem 0.35rem' }}>{result.session_status}</span>
                              </span>
                            )}
                          </div>
                          <button
                            type="button"
                            className="btn btn-secondary"
                            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8rem', padding: '0.4rem 0.8rem', height: 'auto' }}
                            onClick={() => handleOpenInLogs(result)}
                          >
                            <ExternalLink size={14} />
                            Open in Logs
                            <ArrowRight size={14} />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}

            {results.length === 0 && (
              <div className="glass-card" style={{ padding: '3rem', textAlign: 'center', color: 'var(--brown-500)' }}>
                <Search size={48} style={{ color: 'var(--brown-300)', marginBottom: '1rem' }} />
                <h4>No matching results found</h4>
                <p style={{ marginTop: '0.25rem' }}>Try adjusting your keywords, selecting a different organization, or widening search filters.</p>
              </div>
            )}
          </div>
        </div>
      )}

      {!searching && !hasSearched && (
        <div className="glass-card" style={{ padding: '3rem', textAlign: 'center', color: 'var(--brown-500)' }}>
          <Search size={48} style={{ color: 'var(--brown-300)', marginBottom: '1rem' }} />
          <h4>Ready to search</h4>
          <p style={{ marginTop: '0.25rem' }}>Enter keywords and click search to scan the Doceebot memory pipeline.</p>
        </div>
      )}
    </div>
  );
};
