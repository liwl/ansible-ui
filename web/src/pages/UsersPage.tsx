import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { toast } from 'sonner';
import api from '@/services/api';
import { getApiErrorMessage } from '@/utils/http';
import { confirm } from '@/components/ConfirmDialog';
import { Pencil1Icon, PlusCircledIcon, TrashIcon } from '@radix-ui/react-icons';
import { KeyRound, ShieldCheck, User as UserIcon } from 'lucide-react';
import { useTableControls } from '@/hooks/useTableControls';
import { SortableHead, TablePagination } from '@/components/table-controls';

interface User {
  id: number;
  username: string;
  role: 'admin' | 'viewer';
  is_primary: number;
  created_at: string | null;
  last_login: string | null;
}

interface FormState {
  username: string;
  password: string;
  role: 'admin' | 'viewer';
}

const emptyForm: FormState = { username: '', password: '', role: 'viewer' };

function roleBadge(role: string) {
  return role === 'admin'
    ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
    : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300';
}

function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [pwdUser, setPwdUser] = useState<User | null>(null);
  const [newPassword, setNewPassword] = useState('');
  const [isPwdSubmitting, setIsPwdSubmitting] = useState(false);

  const fetchUsers = useCallback(async (silent = false) => {
    if (!silent) setIsLoading(true);
    try {
      const response = await api.get('/api/users');
      setUsers(response.data || []);
    } catch (error) {
      toast.error(getApiErrorMessage(error, '获取用户列表失败'));
    } finally {
      if (!silent) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  // 角色按「管理员→只读」的业务顺序排，时间列按字符串比较（格式为 YYYY-MM-DD HH:MM:SS，可直接比较）
  const accessors = useMemo(() => {
    const roleRank: Record<string, number> = { admin: 0, viewer: 1 };
    return {
      username: (user: User) => user.username,
      role: (user: User) => roleRank[user.role] ?? 9,
      last_login: (user: User) => user.last_login,
      created_at: (user: User) => user.created_at,
    };
  }, []);

  const table = useTableControls<User>({
    data: users,
    accessors,
    defaultSortKey: 'role',
    initialPageSize: 10,
  });

  const openCreate = () => {
    setEditingUser(null);
    setForm(emptyForm);
    setIsFormOpen(true);
  };

  const openEdit = (user: User) => {
    setEditingUser(user);
    setForm({ username: user.username, password: '', role: user.role });
    setIsFormOpen(true);
  };

  const handleSubmit = async () => {
    if (!editingUser) {
      if (!form.username.trim()) {
        toast.error('请输入用户名');
        return;
      }
      if (form.password.length < 6) {
        toast.error('密码至少 6 位');
        return;
      }
    }

    setIsSubmitting(true);
    try {
      if (editingUser) {
        await api.put(`/api/users/${editingUser.id}`, { role: form.role });
        toast.success('已更新用户角色');
      } else {
        await api.post('/api/users', {
          username: form.username.trim(),
          password: form.password,
          role: form.role,
        });
        toast.success('用户已创建');
      }
      setIsFormOpen(false);
      fetchUsers(true);
    } catch (error) {
      toast.error(getApiErrorMessage(error, '保存失败'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResetPassword = async () => {
    if (!pwdUser) return;
    if (newPassword.length < 6) {
      toast.error('密码至少 6 位');
      return;
    }
    setIsPwdSubmitting(true);
    try {
      await api.put(`/api/users/${pwdUser.id}`, { password: newPassword });
      toast.success(`已重置 ${pwdUser.username} 的密码`);
      setPwdUser(null);
      setNewPassword('');
    } catch (error) {
      toast.error(getApiErrorMessage(error, '重置密码失败'));
    } finally {
      setIsPwdSubmitting(false);
    }
  };

  const handleDelete = async (user: User) => {
    const ok = await confirm({
      title: '删除用户',
      description: `确定删除用户「${user.username}」吗？该账号将立即无法登录。`,
      confirmText: '删除',
      destructive: true,
    });
    if (!ok) return;
    try {
      await api.delete(`/api/users/${user.id}`);
      toast.success('用户已删除');
      fetchUsers(true);
    } catch (error) {
      toast.error(getApiErrorMessage(error, '删除失败'));
    }
  };

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">用户管理</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          管理可登录本平台的账号与角色。只读角色可浏览全部数据，但不能执行任何变更操作。
        </p>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4">
          <div>
            <CardTitle>账号列表</CardTitle>
            <CardDescription>
              共 {users.length} 个账号。主管理员由部署环境变量 ADMIN_USERNAME / ADMIN_PASSWORD 决定，不可删除或降级。
            </CardDescription>
          </div>
          <Button onClick={openCreate}>
            <PlusCircledIcon className="mr-1.5 h-4 w-4" />
            新增用户
          </Button>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <SortableHead sortKey="username" activeKey={table.sortKey} dir={table.sortDir} onSort={table.toggleSort}>用户名</SortableHead>
                <SortableHead sortKey="role" activeKey={table.sortKey} dir={table.sortDir} onSort={table.toggleSort}>角色</SortableHead>
                <SortableHead sortKey="last_login" activeKey={table.sortKey} dir={table.sortDir} onSort={table.toggleSort}>最近登录</SortableHead>
                <SortableHead sortKey="created_at" activeKey={table.sortKey} dir={table.sortDir} onSort={table.toggleSort}>创建时间</SortableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {table.pageRows.map(user => (
                <TableRow key={user.id}>
                  <TableCell>
                    <span className="flex items-center gap-2 font-medium">
                      {user.is_primary ? (
                        <ShieldCheck className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                      ) : (
                        <UserIcon className="h-4 w-4 text-muted-foreground" />
                      )}
                      {user.username}
                      {user.is_primary ? (
                        <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[11px] text-blue-700 dark:bg-blue-500/15 dark:text-blue-300">主管理员</span>
                      ) : null}
                    </span>
                  </TableCell>
                  <TableCell>
                    <span className={`rounded px-2 py-0.5 text-xs ${roleBadge(user.role)}`}>
                      {user.role === 'admin' ? '管理员' : '只读'}
                    </span>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{user.last_login || '从未登录'}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{user.created_at || '-'}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        title="编辑角色"
                        onClick={() => openEdit(user)}
                        disabled={Boolean(user.is_primary)}
                      >
                        <Pencil1Icon className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        title={user.is_primary ? '主管理员密码需在部署配置中修改' : '重置密码'}
                        onClick={() => {
                          setPwdUser(user);
                          setNewPassword('');
                        }}
                        disabled={Boolean(user.is_primary)}
                      >
                        <KeyRound className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        title={user.is_primary ? '主管理员不可删除' : '删除'}
                        className="text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300"
                        onClick={() => handleDelete(user)}
                        disabled={Boolean(user.is_primary)}
                      >
                        <TrashIcon className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {users.length === 0 && !isLoading && (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                    暂无用户
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
          <TablePagination
            page={table.page}
            pageCount={table.pageCount}
            pageSize={table.pageSize}
            total={table.total}
            onPageChange={table.setPage}
            onPageSizeChange={table.setPageSize}
          />
        </CardContent>
      </Card>

      <Dialog open={isFormOpen} onOpenChange={setIsFormOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingUser ? '编辑用户' : '新增用户'}</DialogTitle>
            <DialogDescription>
              {editingUser ? '管理员可调整角色，只读用户只能查看数据。' : '新账号创建后即可用该用户名密码登录。'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>用户名</Label>
              <Input
                value={form.username}
                disabled={Boolean(editingUser)}
                placeholder="例如 zhangsan"
                onChange={e => setForm(prev => ({ ...prev, username: e.target.value }))}
              />
            </div>
            {!editingUser && (
              <div className="space-y-2">
                <Label>初始密码</Label>
                <Input
                  type="password"
                  value={form.password}
                  placeholder="至少 6 位"
                  onChange={e => setForm(prev => ({ ...prev, password: e.target.value }))}
                />
              </div>
            )}
            <div className="space-y-2">
              <Label>角色</Label>
              <select
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                value={form.role}
                onChange={e => setForm(prev => ({ ...prev, role: e.target.value as 'admin' | 'viewer' }))}
              >
                <option value="viewer">只读（仅查看）</option>
                <option value="admin">管理员（全部权限）</option>
              </select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsFormOpen(false)}>取消</Button>
            <Button onClick={handleSubmit} disabled={isSubmitting}>
              {isSubmitting ? '保存中...' : '保存'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(pwdUser)} onOpenChange={open => !open && setPwdUser(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>重置密码：{pwdUser?.username}</DialogTitle>
            <DialogDescription>设置一个新密码，保存后该账号原有密码立即失效。</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label>新密码</Label>
            <Input
              type="password"
              value={newPassword}
              placeholder="至少 6 位"
              onChange={e => setNewPassword(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPwdUser(null)}>取消</Button>
            <Button onClick={handleResetPassword} disabled={isPwdSubmitting}>
              {isPwdSubmitting ? '保存中...' : '保存'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default UsersPage;
