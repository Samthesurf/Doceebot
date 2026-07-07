import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { isFirebaseConfigured } from '../firebase';
import { LayoutDashboard, ReceiptText, LogOut, Menu, X, Globe, Cpu, WalletCards } from 'lucide-react';

interface LayoutProps {
  children: React.ReactNode;
  currentPath: string;
  onNavigate: (path: string) => void;
}

export const Layout: React.FC<LayoutProps> = ({ children, currentPath, onNavigate }) => {
  const { user, logout, demoMode, toggleDemoMode } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navItems = [
    { label: 'Overview', path: '/dashboard', icon: <LayoutDashboard size={18} /> },
    { label: 'Token Usage', path: '/token-usage', icon: <WalletCards size={18} /> },
    { label: 'Conversation Logs', path: '/logs', icon: <ReceiptText size={18} /> },
  ];

  const handleNavClick = (path: string) => {
    onNavigate(path);
    setMobileMenuOpen(false);
  };

  const getInitials = (name: string | null) => {
    if (!name) return 'U';
    return name
      .split(' ')
      .map((n) => n[0])
      .join('')
      .substring(0, 2)
      .toUpperCase();
  };

  return (
    <div className="app-container">
      {/* Mobile Header */}
      <div className="mobile-header">
        <div className="sidebar-logo" style={{ marginBottom: 0 }}>
          Docee<span>bot</span>
        </div>
        <button 
          style={{ background: 'none', border: 'none', color: 'var(--brown-700)', cursor: 'pointer' }}
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
        >
          {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div 
          className="fade-in" 
          style={{
            position: 'absolute',
            top: '60px',
            left: 0,
            right: 0,
            background: 'var(--bg-cream)',
            borderBottom: '1px solid var(--brown-100)',
            padding: '1.5rem',
            zIndex: 100,
            display: 'flex',
            flexDirection: 'column',
            gap: '1rem',
            boxShadow: 'var(--shadow-lg)'
          }}
        >
          {navItems.map((item) => (
            <button
              key={item.path}
              className={`nav-link ${currentPath === item.path ? 'active' : ''}`}
              style={{ border: 'none', width: '100%', textAlign: 'left', cursor: 'pointer' }}
              onClick={() => handleNavClick(item.path)}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
          
          <div style={{ borderTop: '1px solid var(--brown-100)', paddingTop: '1rem', marginTop: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
              {user?.picture ? (
                <img src={user.picture} alt="" className="user-avatar" />
              ) : (
                <div className="user-avatar" style={{ display: 'flex', alignItems: 'center', justifySelf: 'center', justifyContent: 'center', fontWeight: 'bold', color: 'white', background: 'var(--brown-700)', fontSize: '0.85rem' }}>
                  {getInitials(user?.name || '')}
                </div>
              )}
              <div className="user-info">
                <span className="user-name">{user?.name || 'User'}</span>
                <span className="user-email">{user?.email || ''}</span>
              </div>
            </div>

            {demoMode && isFirebaseConfigured && (
              <button
                className="btn btn-outline btn-small"
                style={{ width: '100%', marginBottom: '0.5rem' }}
                onClick={() => toggleDemoMode(false)}
              >
                <Globe size={14} />
                Switch to Live
              </button>
            )}

            <button 
              className="btn btn-danger btn-small" 
              style={{ width: '100%' }}
              onClick={logout}
            >
              <LogOut size={14} />
              Logout
            </button>
          </div>
        </div>
      )}

      {/* Desktop Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          Docee<span>bot</span>
        </div>

        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <button
              key={item.path}
              className={`nav-link ${currentPath === item.path ? 'active' : ''}`}
              style={{ border: 'none', width: '100%', cursor: 'pointer' }}
              onClick={() => handleNavClick(item.path)}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </nav>

        {demoMode && (
          <div 
            style={{ 
              background: 'var(--accent-gold-bg)',
              border: '1px solid var(--accent-gold-light)',
              borderRadius: '8px',
              padding: '0.75rem',
              fontSize: '0.8rem',
              color: 'var(--accent-gold)',
              marginBottom: '1rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem'
            }}
          >
            <Cpu size={16} />
            <div>
              <strong>Demo Workspace</strong>
              <div style={{ fontSize: '0.75rem', color: 'var(--brown-500)' }}>Using simulated data</div>
            </div>
          </div>
        )}

        <div className="sidebar-footer">
          <div className="user-profile">
            {user?.picture ? (
              <img src={user.picture} alt="" className="user-avatar" />
            ) : (
              <div className="user-avatar" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 'bold', color: 'white', background: 'var(--brown-700)', fontSize: '0.85rem' }}>
                {getInitials(user?.name || '')}
              </div>
            )}
            <div className="user-info">
              <span className="user-name">{user?.name || 'User'}</span>
              <span className="user-email">{user?.email || ''}</span>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {demoMode && isFirebaseConfigured && (
              <button
                className="btn btn-outline btn-small"
                style={{ width: '100%' }}
                onClick={() => toggleDemoMode(false)}
              >
                <Globe size={14} />
                Switch to Live
              </button>
            )}

            <button 
              className="btn btn-secondary btn-small" 
              style={{ width: '100%' }}
              onClick={logout}
            >
              <LogOut size={14} />
              Sign Out
            </button>
          </div>
        </div>
      </aside>

      <main className="main-content">
        {children}
      </main>
    </div>
  );
};
