import React, { useState } from 'react';
import { Cpu, Eye, EyeOff, KeyRound, Mail, ShieldAlert } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { isFirebaseConfigured } from '../firebase';

const googleLogoUrl = `${import.meta.env.BASE_URL}google_g_logo.svg`;

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
  const [showPassword, setShowPassword] = useState(false);
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
          <img
            src={`${import.meta.env.BASE_URL}doceebot-icon.svg`}
            alt="Doceebot"
            width={56}
            height={56}
            style={{ borderRadius: 14 }}
          />
        </div>

        <h1>Doceebot</h1>
        <p>Supervisor &amp; Administrator Dashboard</p>

        {error && (
          <div className="badge badge-error login-error">
            {error}
          </div>
        )}

        {isFirebaseConfigured ? (
          <div className="auth-panel">
            <form className="auth-form" onSubmit={handleEmailAuth}>
              <label className="auth-field">
                <span>Email address</span>
                <div className="input-shell">
                  <Mail className="auth-field-icon" size={18} />
                  <input
                    className="form-input input-with-icon"
                    type="email"
                    placeholder="engineer@example.com"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    disabled={loading}
                    autoComplete="email"
                  />
                </div>
              </label>

              <label className="auth-field">
                <span>Password</span>
                <div className="input-shell">
                  <KeyRound className="auth-field-icon" size={18} />
                  <input
                    className="form-input input-with-icon"
                    type={showPassword ? 'text' : 'password'}
                    placeholder="Enter your password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    disabled={loading}
                    autoComplete={authMode === 'login' ? 'current-password' : 'new-password'}
                  />
                  <button
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    className="auth-password-toggle"
                    disabled={loading}
                    onClick={() => setShowPassword((value) => !value)}
                    type="button"
                  >
                    {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                  </button>
                </div>
              </label>

              <button className="btn btn-primary auth-submit" type="submit" disabled={loading}>
                {loading ? (
                  <div className="spinner spinner-small" />
                ) : authMode === 'login' ? (
                  'Sign in'
                ) : (
                  'Create email account'
                )}
              </button>
            </form>

            <div className="auth-divider" aria-hidden="true">
              <span>OR</span>
            </div>

            <button
              className="google-button"
              type="button"
              onClick={handleGoogleLogin}
              disabled={loading}
            >
              {loading ? (
                <div className="spinner spinner-small" />
              ) : (
                <>
                  <img className="google-logo" src={googleLogoUrl} alt="" aria-hidden="true" />
                  <span>Sign in with Google</span>
                </>
              )}
            </button>

            <button
              className="link-button auth-switch"
              type="button"
              onClick={() => setAuthMode(authMode === 'login' ? 'register' : 'login')}
              disabled={loading}
            >
              {authMode === 'login'
                ? 'Need an email/password account? Register here.'
                : 'Already registered? Sign in instead.'}
            </button>

            <div className="auth-helper">Authorized emails only.</div>

            <div className="demo-entry">
              <button
                className="btn btn-secondary btn-small"
                type="button"
                onClick={() => {
                  toggleDemoMode(true);
                  loginDemo();
                }}
              >
                Preview demo workspace
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
