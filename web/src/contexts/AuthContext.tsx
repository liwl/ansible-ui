import React, { useEffect, useMemo, useState } from 'react';
import api from '@/services/api';
import { AuthContext, type UserRole } from '@/contexts/auth-context';
import { authStorage } from '@/contexts/auth-storage';

const normalizeRole = (value: string | null): UserRole | null => {
  if (value === 'admin' || value === 'viewer') return value;
  return null;
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => {
    return authStorage.getAuth();
  });

  const [token, setToken] = useState<string | null>(() => {
    return authStorage.getToken();
  });

  const [username, setUsername] = useState<string | null>(() => {
    return authStorage.getUsername();
  });

  const [role, setRole] = useState<UserRole | null>(() => {
    return normalizeRole(authStorage.getRole());
  });

  useEffect(() => {
    const checkAuthExpiry = () => {
      const currentAuth = authStorage.getAuth();
      if (isAuthenticated !== currentAuth) {
        setIsAuthenticated(currentAuth);
        if (!currentAuth) {
          setToken(null);
          setUsername(null);
          setRole(null);
        }
      }
    };
    
    const interval = setInterval(checkAuthExpiry, 60000);
    return () => clearInterval(interval);
  }, [isAuthenticated]);

  const login = async (loginName: string, password: string): Promise<boolean> => {
    try {
      const response = await api.post('/api/login', { username: loginName, password });
      if (response.data.success) {
        const jwtToken = response.data.token as string;
        const nextUsername = (response.data.username as string) || loginName;
        const nextRole = normalizeRole((response.data.role as string) || 'admin') ?? 'viewer';
        setIsAuthenticated(true);
        setToken(jwtToken);
        setUsername(nextUsername);
        setRole(nextRole);
        authStorage.setAuth(true, jwtToken, 5, nextUsername, nextRole);
        return true;
      } else {
        setIsAuthenticated(false);
        setToken(null);
        setUsername(null);
        setRole(null);
        authStorage.clearAuth();
        return false;
      }
    } catch {
      setIsAuthenticated(false);
      setToken(null);
      setUsername(null);
      setRole(null);
      authStorage.clearAuth();
      return false;
    }
  };

  const logout = () => {
    setIsAuthenticated(false);
    setToken(null);
    setUsername(null);
    setRole(null);
    authStorage.clearAuth();
  };

  const isAdmin = role === 'admin';

  const value = useMemo(
    () => ({ isAuthenticated, login, logout, token, username, role, isAdmin }),
    // login/logout 是稳定闭包，无需进入依赖
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [isAuthenticated, token, username, role, isAdmin],
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};
