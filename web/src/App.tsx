import React, { lazy, Suspense } from 'react';
import { BrowserRouter as Router, Route, Routes, Navigate } from 'react-router-dom';
import LoginPage from './pages/LoginPage';
import AppShell from './components/AppShell';
import { ConfirmDialogProvider } from './components/ConfirmDialog';

const MainPage = lazy(() => import('./pages/MainPage'));
const PlaybooksPage = lazy(() => import('./pages/PlaybooksPage'));
const HistoryPage = lazy(() => import('./pages/HistoryPage'));
const FilesPage = lazy(() => import('./pages/FilesPage'));
const UsersPage = lazy(() => import('./pages/UsersPage'));
const TerminalPage = lazy(() => import('./pages/TerminalPage'));
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from './contexts/AuthContext';
import { authStorage } from './contexts/auth-storage';
import { useAuth } from './contexts/use-auth';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  const isLocalAuth = authStorage.getAuth();
  if (isAuthenticated || isLocalAuth) {
    return <>{children}</>;
  }
  return <Navigate to="/login" replace />;
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const { isAdmin } = useAuth();
  if (!isAdmin) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}

function MainLayout() {
  return (
    <AppShell>
      <MainPage />
    </AppShell>
  );
}

function App() {
  return (
    <AuthProvider>
      <ConfirmDialogProvider>
      <Router>
        <Suspense fallback={
          <div className="flex min-h-screen items-center justify-center bg-background">
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
              <span className="text-sm text-muted-foreground">加载中...</span>
            </div>
          </div>
        }>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route 
            path="/" 
            element={
              <ProtectedRoute>
                <MainLayout />
              </ProtectedRoute>
            }
          />
          <Route
            path="/playbooks"
            element={
              <ProtectedRoute>
                <AppShell>
                  <PlaybooksPage />
                </AppShell>
              </ProtectedRoute>
            }
          />
          <Route
            path="/history"
            element={
              <ProtectedRoute>
                <AppShell>
                  <HistoryPage />
                </AppShell>
              </ProtectedRoute>
            }
          />
          <Route
            path="/files"
            element={
              <ProtectedRoute>
                <AppShell>
                  <FilesPage />
                </AppShell>
              </ProtectedRoute>
            }
          />
          <Route
            path="/users"
            element={
              <ProtectedRoute>
                <AdminRoute>
                  <AppShell>
                    <UsersPage />
                  </AppShell>
                </AdminRoute>
              </ProtectedRoute>
            }
          />
          <Route 
            path="/terminal/:hostId"
            element={<TerminalPage />}
          />
          <Route 
            path="*" 
            element={
              <AuthRedirect />
            } 
          />
        </Routes>
        </Suspense>
      </Router>
      <Toaster richColors />
      </ConfirmDialogProvider>
    </AuthProvider>
  );
}

function AuthRedirect() {
  const { isAuthenticated } = useAuth();
  const isLocalAuth = authStorage.getAuth();
  
  return (isAuthenticated || isLocalAuth) ? <Navigate to="/" replace /> : <Navigate to="/login" replace />;
}

export default App;
