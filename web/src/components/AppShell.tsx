import type { ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { LogOut, Server } from 'lucide-react';
import { useAuth } from '@/contexts/use-auth';
import ThemeToggle from '@/components/ThemeToggle';

interface AppShellProps {
  children: ReactNode;
}

function AppShell({ children }: AppShellProps) {
  const { logout, username, isAdmin } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const navItems = [
    { path: '/', label: '主机管理', adminOnly: false },
    { path: '/playbooks', label: 'Playbook 管理', adminOnly: false },
    { path: '/files', label: '文件管理', adminOnly: false },
    { path: '/history', label: '执行历史', adminOnly: false },
    { path: '/users', label: '用户管理', adminOnly: true },
  ].filter(item => !item.adminOnly || isAdmin);

  const navButtonClass = (path: string) =>
    `shrink-0 rounded px-2.5 py-1 text-sm transition-colors ${
      location.pathname === path ? 'bg-white/20 font-medium' : 'hover:bg-white/10'
    }`;

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="flex h-12 shrink-0 items-center justify-between bg-primary px-4 text-primary-foreground shadow-sm">
        <div className="flex items-center gap-6">
          <button
            type="button"
            onClick={() => navigate('/')}
            className="flex items-center gap-2.5 text-base font-semibold"
          >
            <span className="flex h-6 w-6 items-center justify-center rounded bg-white/20">
              <Server size={14} />
            </span>
            Ansible 运维管理平台
          </button>
          <nav className="hidden items-center gap-1 md:flex">
            {navItems.map(item => (
              <button
                key={item.path}
                type="button"
                onClick={() => navigate(item.path)}
                className={navButtonClass(item.path)}
              >
                {item.label}
              </button>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="hidden items-center gap-1.5 opacity-90 sm:flex">
            当前用户：{username || '未知'}
            {!isAdmin && (
              <span className="rounded bg-white/20 px-1.5 py-0.5 text-[11px] leading-none">只读</span>
            )}
          </span>
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-white/20 text-xs">
            {(username || '管').slice(0, 1).toUpperCase()}
          </span>
          <ThemeToggle />
          <button
            type="button"
            onClick={logout}
            className="flex h-7 items-center gap-1.5 rounded border border-white/40 bg-white/15 px-2.5 text-xs text-white transition-colors hover:bg-white/25"
          >
            <LogOut size={13} />
            退出
          </button>
        </div>
      </header>

      <nav className="flex items-center gap-1 overflow-x-auto border-b border-border bg-primary/95 px-2 py-1.5 text-primary-foreground md:hidden">
        {navItems.map(item => (
          <button
            key={item.path}
            type="button"
            onClick={() => navigate(item.path)}
            className={navButtonClass(item.path)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <main className="flex-1">{children}</main>
    </div>
  );
}

export default AppShell;
