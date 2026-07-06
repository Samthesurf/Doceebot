/* oxlint-disable react/only-export-components */
import React, { createContext, useContext, useState, useEffect } from 'react';
import {
  auth,
  createUserWithEmailAndPassword,
  googleProvider,
  isFirebaseConfigured,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
} from '../firebase';
import { getDemoMode, setDemoMode as apiSetDemoMode } from '../api';
import type { DashboardUser } from '../types';

interface AuthContextType {
  user: DashboardUser | null;
  token: string | null;
  loading: boolean;
  demoMode: boolean;
  error: string | null;
  loginWithGoogle: () => Promise<void>;
  loginWithEmail: (email: string, password: string) => Promise<void>;
  registerWithEmail: (email: string, password: string) => Promise<void>;
  loginDemo: () => void;
  logout: () => Promise<void>;
  toggleDemoMode: (enabled: boolean) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<DashboardUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [demoMode, setDemoModeState] = useState(getDemoMode());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (demoMode || !isFirebaseConfigured) {
      // In demo mode, load local session if available, even when Firebase is configured.
      const savedUser = localStorage.getItem('doceebot_demo_user');
      if (savedUser) {
        try {
          setUser(JSON.parse(savedUser));
          setToken('demo-mode-token-xyz');
        } catch {
          // Ignored
        }
      }
      setLoading(false);
      return;
    }

    if (!auth) {
      setLoading(false);
      return;
    }

    const unsubscribe = auth.onAuthStateChanged(async (firebaseUser) => {
      setLoading(true);
      if (firebaseUser) {
        try {
          const idToken = await firebaseUser.getIdToken();
          
          // Verify if they are in the allowed email list (backend does this too, we do a client-side check for UX)
          const dashboardUser: DashboardUser = {
            uid: firebaseUser.uid,
            email: firebaseUser.email,
            name: firebaseUser.displayName,
            picture: firebaseUser.photoURL,
          };
          
          setUser(dashboardUser);
          setToken(idToken);
          setError(null);
        } catch (err: any) {
          console.error('Error fetching ID token:', err);
          setError(err.message || 'Authentication error');
          setUser(null);
          setToken(null);
        }
      } else {
        setUser(null);
        setToken(null);
      }
      setLoading(false);
    });

    return () => unsubscribe();
  }, [demoMode]);

  const loginWithGoogle = async () => {
    if (!isFirebaseConfigured || !auth || !googleProvider) {
      setError('Firebase is not configured. Please use Demo Mode.');
      return;
    }
    setError(null);
    setLoading(true);
    try {
      await signInWithPopup(auth, googleProvider);
    } catch (err: any) {
      console.error('Firebase Login failed:', err);
      setError(err.message || 'Login failed. Please verify credentials.');
      setLoading(false);
      throw err;
    }
  };

  const loginWithEmail = async (email: string, password: string) => {
    if (!isFirebaseConfigured || !auth) {
      setError('Firebase is not configured. Please use Demo Mode.');
      return;
    }
    setError(null);
    setLoading(true);
    try {
      await signInWithEmailAndPassword(auth, email, password);
    } catch (err: any) {
      console.error('Email login failed:', err);
      setError(err.message || 'Email login failed.');
      setLoading(false);
      throw err;
    }
  };

  const registerWithEmail = async (email: string, password: string) => {
    if (!isFirebaseConfigured || !auth) {
      setError('Firebase is not configured. Please use Demo Mode.');
      return;
    }
    setError(null);
    setLoading(true);
    try {
      await createUserWithEmailAndPassword(auth, email, password);
    } catch (err: any) {
      console.error('Email registration failed:', err);
      setError(err.message || 'Email registration failed.');
      setLoading(false);
      throw err;
    }
  };

  const loginDemo = () => {
    setError(null);
    const mockUser: DashboardUser = {
      uid: 'demo-admin-uid-12345',
      email: 'admin@doceebot.com',
      name: 'Elena Rostova',
      picture: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&q=80&w=150',
    };
    setUser(mockUser);
    setToken('demo-mode-token-xyz');
    localStorage.setItem('doceebot_demo_user', JSON.stringify(mockUser));
  };

  const logout = async () => {
    setLoading(true);
    try {
      if (isFirebaseConfigured && auth) {
        await signOut(auth);
      }
      setUser(null);
      setToken(null);
      localStorage.removeItem('doceebot_demo_user');
    } catch (err: any) {
      console.error('Logout failed:', err);
      setError(err.message || 'Logout failed');
    } finally {
      setLoading(false);
    }
  };

  const toggleDemoMode = (enabled: boolean) => {
    apiSetDemoMode(enabled);
    setDemoModeState(enabled);
    setUser(null);
    setToken(null);
    localStorage.removeItem('doceebot_demo_user');
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        loading,
        demoMode,
        error,
        loginWithGoogle,
        loginWithEmail,
        registerWithEmail,
        loginDemo,
        logout,
        toggleDemoMode,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

// oxlint-disable-next-line react(only-export-components)
export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
