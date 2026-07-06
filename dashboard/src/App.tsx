import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { LoginView } from './components/LoginView';
import { Layout } from './components/Layout';
import { DashboardView } from './components/DashboardView';
import { LogsView } from './components/LogsView';

const AppRoutes: React.FC = () => {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  if (loading) {
    return (
      <div 
        style={{ 
          display: 'flex', 
          flexDirection: 'column', 
          alignItems: 'center', 
          justifyContent: 'center', 
          minHeight: '100vh', 
          gap: '1rem',
          backgroundColor: 'var(--bg-milk)' 
        }}
      >
        <div className="spinner" style={{ width: '40px', height: '40px', borderWidth: '4px' }} />
        <p style={{ color: 'var(--brown-500)', fontFamily: 'var(--font-display)', fontWeight: 500 }}>
          Initializing system shell...
        </p>
      </div>
    );
  }

  // Redirect unauthenticated users to /dashboard/login
  if (!user) {
    return (
      <Routes>
        <Route path="/dashboard/login" element={<LoginView />} />
        <Route path="*" element={<Navigate to="/dashboard/login" replace />} />
      </Routes>
    );
  }

  // Render layouts for authenticated users
  return (
    <Layout currentPath={location.pathname} onNavigate={(path) => navigate(path)}>
      <Routes>
        <Route path="/dashboard" element={<DashboardView />} />
        <Route path="/logs" element={<LogsView />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Layout>
  );
};

const App: React.FC = () => {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
};

export default App;
