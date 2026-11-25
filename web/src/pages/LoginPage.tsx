import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LockKeyhole, Server, User } from 'lucide-react';
import { useAuth } from '@/contexts/use-auth';

function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const navigate = useNavigate();
  const { login } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage('');
    setIsLoading(true);

    const success = await login(username, password);
    setIsLoading(false);
    if (success) {
      navigate('/', { replace: true });
    } else {
      setErrorMessage('用户名或密码错误');
    }
  };

  return (
    <div
      className="flex min-h-screen items-center justify-center p-4"
      style={{ background: 'linear-gradient(135deg, #2b6be0 0%, #3b82f6 55%, #6aa5f5 100%)' }}
    >
      <div className="w-full max-w-[400px] rounded-[10px] bg-card text-card-foreground px-9 pb-7 pt-10 shadow-[0_18px_50px_rgba(15,45,95,0.28)]">
        <div className="mx-auto mb-[18px] flex h-[52px] w-[52px] items-center justify-center rounded-xl bg-primary shadow-[0_6px_14px_rgba(43,107,224,0.35)]">
          <Server size={28} className="text-primary-foreground" />
        </div>
        <h1 className="text-center text-[21px] font-semibold tracking-wide">Ansible 运维管理平台</h1>
        <p className="mb-[30px] mt-2 text-center text-[13px] text-muted-foreground">欢迎使用智能运维管理平台</p>

        <form onSubmit={handleSubmit}>
          <div className="mb-[18px]">
            <Label htmlFor="username" className="mb-2 block text-[13px] text-foreground/80">用户名</Label>
            <div className="relative">
              <User size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="username"
                type="text"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={isLoading}
                placeholder="请输入用户名"
                className="h-[42px] pl-10 placeholder:opacity-60"
              />
            </div>
          </div>

          <div className="mb-[18px]">
            <Label htmlFor="password" className="mb-2 block text-[13px] text-foreground/80">密码</Label>
            <div className="relative">
              <LockKeyhole size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isLoading}
                placeholder="请输入密码"
                className="h-[42px] pl-10 placeholder:opacity-60"
              />
            </div>
            {errorMessage && (
              <div className="mt-2 text-sm text-destructive">{errorMessage}</div>
            )}
          </div>

          <Button type="submit" className="mt-1.5 h-[42px] w-full text-[15px] tracking-[4px]" disabled={isLoading}>
            {isLoading ? '登录中...' : '登录'}
          </Button>
        </form>

        <div className="mt-6 text-center text-xs text-muted-foreground">© 2026 · Ansible 运维管理平台</div>
      </div>
    </div>
  );
}

export default LoginPage;
