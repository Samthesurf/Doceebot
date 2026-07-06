import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { isFirebaseConfigured } from '../firebase';
import { Lock, ShieldAlert, Cpu } from 'lucide-react';

export const LoginView: React.FC = () => {
  const {
    loginWithGoogle,
    loginWithEmail,
    registerWithEmail,
    loginDemo,
    error,
    loading,
    toggleDemoMode,
    demoMode,
  } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');

  const handleGoogleLogin = async () => {
    try {
      await loginWithGoogle();
    } catch (err) {
      console.error(err);
    }
  };

  const handleEmailAuth = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!email.trim() || !password.trim()) return;
    try {
      if (authMode === 'login') {
        await loginWithEmail(email.trim(), password);
      } else {
        await registerWithEmail(email.trim(), password);
      }
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="login-container">
      <div className="glass-card login-card fade-in">
        <div className="login-icon">
          <Lock size={32} />
        </div>
        
        <h1>Doceebot</h1>
        <p>Supervisor &amp; Administrator Dashboard</p>

        {error && (
          <div className="badge badge-error" style={{ display: 'block', margin: '0 auto 1.5rem', width: 'fit-content' }}>
            {error}
          </div>
        )}

        {isFirebaseConfigured ? (
          <div>
            <div className="demo-badge">Firebase Enabled</div>
            <button 
              className="btn btn-primary" 
              style={{ width: '100%', marginBottom: '1rem' }} 
              onClick={handleGoogleLogin}
              disabled={loading}
            >
              {loading ? <div className="spinner" style={{ width: '18px', height: '18px' }} /> : 'Sign in with Google'}
            </button>

            <form onSubmit={handleEmailAuth} style={{ display: 'grid', gap: '0.75rem', marginBottom: '1rem' }}>
              <input
                className="form-input"
                type="email"
                placeholder="Admin email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                disabled={loading}
                autoComplete="email"
              />
              <input
                className="form-input"
                type="password"
                placeholder="Password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                disabled={loading}
                autoComplete={authMode === 'login' ? 'current-password' : 'new-password'}
              />
              <button className="btn btn-secondary" type="submit" disabled={loading}>
                {authMode === 'login' ? 'Sign in with email' : 'Create email account'}
              </button>
              <button
                className="link-button"
                type="button"
                onClick={() => setAuthMode(authMode === 'login' ? 'register' : 'login')}
                disabled={loading}
              >
                {authMode === 'login'
                  ? 'Need an email/password account? Register here.'
                  : 'Already registered? Sign in instead.'}
              </button>
            </form>
            <div style={{ fontSize: '0.8rem', color: 'var(--brown-400)' }}>
              Authorized emails only.
            </div>
            
            <div style={{ marginTop: '2rem', borderTop: '1px solid var(--brown-100)', paddingTop: '1rem' }}>
              <button 
                className="btn btn-secondary btn-small"
                onClick={() => {
                  toggleDemoMode(true);
                  loginDemo();
                }}
              >
                Or enter Demo mode
              </button>
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div 
              style={{ 
                background: 'rgba(200, 150, 62, 0.08)',
                border: '1px solid #FFE0B2',
                borderRadius: '8px',
                padding: '1rem',
                fontSize: '0.85rem',
                textAlign: 'left',
                color: 'var(--brown-800)'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 'bold', marginBottom: '0.5rem' }}>
                <ShieldAlert size={16} style={{ color: 'var(--accent-gold)' }} />
                Firebase Configuration Missing
              </div>
              Vite environment variables (e.g. <code>VITE_FIREBASE_API_KEY</code>) are not defined. The app will run in Demo Mode.
            </div>

            <button 
              className="btn btn-primary" 
              style={{ width: '100%' }}
              onClick={loginDemo}
              disabled={loading}
            >
              <Cpu size={16} />
              Launch Demo Workspace
            </button>

            {demoMode && (
              <div style={{ fontSize: '0.8rem', color: 'var(--brown-500)' }}>
                You are currently previewing with offline mock data.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
