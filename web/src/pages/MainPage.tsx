import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger, DialogClose } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import api from '@/services/api';
import { PlusCircledIcon, Pencil1Icon, TrashIcon, CheckCircledIcon, CrossCircledIcon, PlayIcon, UploadIcon, ReaderIcon, ReloadIcon, InfoCircledIcon } from '@radix-ui/react-icons';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger, SheetFooter, SheetClose } from "@/components/ui/sheet";
import FileUpload from '@/components/FileUpload';
import { Checkbox } from "@/components/ui/checkbox";
import { authStorage } from '@/contexts/auth-storage';
import { useAuth } from '@/contexts/use-auth';
import { TerminalIcon, Github, Search, Trash2 } from 'lucide-react';
import PlaybookExecutor from '@/components/PlaybookExecutor';
import { prepareHostData } from '@/utils/crypto';
import { Switch } from "@/components/ui/switch";
import { getApiErrorMessage } from '@/utils/http';
import { confirm } from '@/components/ConfirmDialog';
import { useTableControls } from '@/hooks/useTableControls';
import { SortableHead, TablePagination } from '@/components/table-controls';

interface Host {
  id: number;
  comment: string;
  address: string;
  username: string;
  port: number;
  password?: string;
  status?: 'checking' | 'success' | 'unreachable' | 'failed' | null;
  is_password_encrypted?: boolean;
  auth_method?: 'password' | 'key';
  private_key_path?: string;
  tag?: string | null;
  last_status?: string | null;
  last_checked?: string | null;
}

interface AccessLog {
  id: number;
  access_time: string;
  ip_address: string;
  path: string;
  status_code: number;
  username?: string | null;
  method?: string | null;
}

function MainPage() {
  const [hosts, setHosts] = useState<Host[]>([]);
  const [selectedHostIds, setSelectedHostIds] = useState<number[]>([]);
  const [command, setCommand] = useState('');
  const [commandLogs, setCommandLogs] = useState<string[]>([]);
  const [isLoadingHosts, setIsLoadingHosts] = useState(false);
  const [isExecutingCommand, setIsExecutingCommand] = useState(false);
  const [isAddingHost, setIsAddingHost] = useState(false);
  const [isEditingHost, setIsEditingHost] = useState(false);
  const [editingHost, setEditingHost] = useState<Host | null>(null);
  const [batchInput, setBatchInput] = useState('');
  const [batchKeyPath, setBatchKeyPath] = useState('');
  const [accessLogs, setAccessLogs] = useState<AccessLog[]>([]);
  const [isLoadingAccessLogs, setIsLoadingAccessLogs] = useState(false);
  const [accessLogIpFilter, setAccessLogIpFilter] = useState('');
  const [accessLogPathFilter, setAccessLogPathFilter] = useState('');
  const [accessLogUserFilter, setAccessLogUserFilter] = useState('');
  const [accessLogUsers, setAccessLogUsers] = useState<string[]>([]);
  const [isUploadDialogOpen, setIsUploadDialogOpen] = useState(false);
  const [uploadTarget, setUploadTarget] = useState<'selected' | 'all' | null>(null);
  const [isBatchAddOpen, setIsBatchAddOpen] = useState(false);
  const [isAuthChecking, setIsAuthChecking] = useState(true);
  const [isPlaybookDialogOpen, setIsPlaybookDialogOpen] = useState(false);
  const [playbookTarget, setPlaybookTarget] = useState<'selected' | 'all' | null>(null);
  const [isLogSheetOpen, setIsLogSheetOpen] = useState(false);
  const [hostSearch, setHostSearch] = useState('');
  const [hostTagFilter, setHostTagFilter] = useState('');
  const [batchTag, setBatchTag] = useState('');
  const [isBatchDeleting, setIsBatchDeleting] = useState(false);
  const [isPingingAll, setIsPingingAll] = useState(false);
  const [useKeyAuth, setUseKeyAuth] = useState(() => {
    const saved = localStorage.getItem('useKeyAuth');
    return saved ? JSON.parse(saved) : false;
  });

  const navigate = useNavigate();
  const { isAuthenticated, isAdmin } = useAuth();

  const availableTags = useMemo(() => {
    const tags = new Set<string>();
    hosts.forEach(h => {
      const t = (h.tag ?? '').trim();
      if (t) tags.add(t);
    });
    return Array.from(tags).sort();
  }, [hosts]);

  // 分组被改名或删除后，当前筛选值可能已不存在，自动回到「全部分组」
  useEffect(() => {
    if (hostTagFilter && !availableTags.includes(hostTagFilter)) {
      setHostTagFilter('');
    }
  }, [availableTags, hostTagFilter]);

  const filteredHosts = useMemo(() => {
    const keyword = hostSearch.trim().toLowerCase();
    return hosts.filter(host => {
      if (hostTagFilter && (host.tag ?? '').trim() !== hostTagFilter) return false;
      if (!keyword) return true;
      return [host.comment, host.address, host.username, host.tag].some(value =>
        (value ?? '').toLowerCase().includes(keyword)
      );
    });
  }, [hosts, hostSearch, hostTagFilter]);

  // 主机表排序规则：状态按「在线→检查中→异常→离线→未检查」的业务顺序排，而不是按字母
  const hostAccessors = useMemo(() => {
    const statusRank: Record<string, number> = {
      success: 1,
      checking: 2,
      failed: 3,
      unreachable: 4,
    };
    return {
      comment: (host: Host) => host.comment,
      tag: (host: Host) => host.tag,
      address: (host: Host) => host.address,
      username: (host: Host) => host.username,
      port: (host: Host) => host.port,
      status: (host: Host) => statusRank[host.status ?? ''] ?? 99,
    };
  }, []);

  const hostTable = useTableControls<Host>({
    data: filteredHosts,
    accessors: hostAccessors,
    initialPageSize: 10,
  });

  // 筛选条件变化后，把已不在结果集中的选中项清掉，
  // 否则批量删除会把筛掉的、屏幕上看不见的主机一起删了
  useEffect(() => {
    const visible = new Set(filteredHosts.map(h => h.id));
    setSelectedHostIds(prev => {
      const next = prev.filter(id => visible.has(id));
      return next.length === prev.length ? prev : next;
    });
  }, [filteredHosts]);

  const accessLogAccessors = useMemo(() => ({
    time: (log: AccessLog) => log.access_time,
    username: (log: AccessLog) => log.username,
    ip: (log: AccessLog) => log.ip_address,
    method: (log: AccessLog) => log.method,
    path: (log: AccessLog) => log.path,
    status_code: (log: AccessLog) => log.status_code,
  }), []);

  const accessLogTable = useTableControls<AccessLog>({
    data: accessLogs,
    accessors: accessLogAccessors,
    defaultSortKey: 'time',
    defaultSortDir: 'desc',
    initialPageSize: 20,
  });

  const statusCounts = useMemo(() => {
    const counts = { total: hosts.length, online: 0, offline: 0, failed: 0, unchecked: 0 };
    hosts.forEach(h => {
      if (h.status === 'success') counts.online++;
      else if (h.status === 'unreachable') counts.offline++;
      else if (h.status === 'failed') counts.failed++;
      else counts.unchecked++;
    });
    return counts;
  }, [hosts]);

  const lastCheckedAt = useMemo(() => {
    const times = hosts
      .map(h => h.last_checked)
      .filter((t): t is string => !!t)
      .sort();
    return times.length ? times[times.length - 1] : null;
  }, [hosts]);

  const notifyRequestError = useCallback((title: string, logMessage: string, error: unknown, fallback = "发生未知错误") => {
    console.error(logMessage, error);
    toast.error(title, {
      description: getApiErrorMessage(error, fallback),
    });
  }, []);

  const fetchHosts = useCallback(async (silent = false) => {
    if (!silent) setIsLoadingHosts(true);
    try {
      const response = await api.get<Host[]>('/api/hosts');
      // 后端定时巡检会持久化 last_status，页面加载/刷新后直接沿用
      const hostsWithStatus = response.data.map(host => ({
        ...host,
        status: (host.last_status as Host['status']) ?? null
      }));
      setHosts(hostsWithStatus);
    } catch (error) {
      notifyRequestError("获取主机列表失败", "Failed to fetch hosts:", error, "无法连接到服务器");
    } finally {
      setIsLoadingHosts(false);
    }
  }, [notifyRequestError]);

  // 后端定时巡检会更新状态，前端每 30 秒静默拉取一次（不闪 loading）
  useEffect(() => {
    const timer = setInterval(() => { void fetchHosts(true); }, 30000);
    return () => clearInterval(timer);
  }, [fetchHosts]);

  useEffect(() => {
    const checkAuth = () => {
      try {
        const isLocalAuth = authStorage.getAuth();

        if (!isAuthenticated && !isLocalAuth) {
          navigate('/login');
          return false;
        }
        return true;
      } catch {
        return false;
      }
    };

    const isAuthed = checkAuth();

    if (isAuthed) {
      void fetchHosts();
    }

    setIsAuthChecking(false);
  }, [fetchHosts, isAuthenticated, navigate]);

  useEffect(() => {
    localStorage.setItem('useKeyAuth', JSON.stringify(useKeyAuth));
  }, [useKeyAuth]);

  const fetchAccessLogs = async (ipFilter = '', pathFilter = '', userFilter = '') => {
    setIsLoadingAccessLogs(true);
    try {
      const response = await api.get<AccessLog[]>('/api/access-logs', {
        params: { ip: ipFilter, path: pathFilter, username: userFilter }
      });
      setAccessLogs(response.data);
    } catch (error) {
      notifyRequestError("获取访问日志失败", "Failed to fetch access logs:", error, "无法连接到服务器");
    } finally {
      setIsLoadingAccessLogs(false);
    }
  };

  const fetchAccessLogUsers = async () => {
    try {
      const response = await api.get<string[]>('/api/access-logs/users');
      setAccessLogUsers(response.data || []);
    } catch {
      // 筛选下拉失败不影响日志展示
    }
  };

  const handleAddHosts = async () => {
    if (!batchInput.trim()) {
      toast.error("错误", { description: "请输入主机信息" });
      return;
    }
    const lines = batchInput.trim().split('\n');
    const hostsData: Omit<Host, 'id'>[] = [];
    const errors: string[] = [];
    const expectedParts = useKeyAuth ? 4 : 5;
    const formatString = useKeyAuth ? "'备注 地址 用户名 端口'" : "'备注 地址 用户名 端口 密码'";

    lines.forEach((line, index) => {
      if (line.trim() === '') return;
      const parts = line.trim().split(/\s+/);
      if (parts.length !== expectedParts) {
        errors.push(`第${index + 1}行：格式错误，应为 ${formatString}`);
      } else {
        const [comment, address, username, portStr, password] = parts;
        const port = parseInt(portStr, 10);
        if (isNaN(port)) {
          errors.push(`第${index + 1}行：端口号 '${portStr}' 无效`);
        } else {
          hostsData.push({
            comment,
            address,
            username,
            port,
            password: useKeyAuth ? '' : password,
            private_key_path: useKeyAuth ? batchKeyPath.trim() : undefined,
            tag: batchTag.trim() || undefined
          });
        }
      }
    });
    if (errors.length > 0) {
      errors.forEach(err => toast.error("输入错误", { description: err }));
      return;
    }
    if (hostsData.length === 0) {
      toast.error("错误", { description: "未找到有效的主机信息" });
      return;
    }
    setIsAddingHost(true);
    try {
      const processedHostsData = hostsData.map(host => prepareHostData(host, undefined, useKeyAuth));
      const response = await api.post('/api/hosts/batch', processedHostsData);
      toast.success("成功", { description: response.data.message || `成功添加 ${response.data.count} 台主机` });
      setBatchInput('');
      setBatchTag('');
      void fetchHosts();
      setIsBatchAddOpen(false); // Close dialog on success
    } catch (error) {
      notifyRequestError("添加主机失败", "Failed to add hosts:", error);
    } finally {
      setIsAddingHost(false);
    }
  };

  const handleEditHost = (host: Host) => {
    const hostWithDefaults = {
      ...host,
      auth_method: host.auth_method || 'password'
    };
    setEditingHost(hostWithDefaults);
  };

  const handleSaveEdit = async (editedHost: Host) => {
    if (!editingHost) return;
    setIsEditingHost(true);
    try {
      const dataToSend = prepareHostData(editedHost, editingHost, editedHost.auth_method === 'key');

      await api.put(`/api/hosts/${editingHost.id}`, dataToSend);
      toast.success("成功", { description: "主机信息已更新" });
      setEditingHost(null);
      void fetchHosts();
    } catch (error) {
      notifyRequestError("更新主机失败", "Failed to update host:", error);
    } finally {
      setIsEditingHost(false);
    }
  };

  const handleDeleteHost = async (hostId: number) => {
    const host = hosts.find(h => h.id === hostId);
    if (!await confirm({
      title: '删除主机',
      description: `确定要删除主机「${host?.comment || hostId}」(${host?.address || ''}) 吗？此操作不可撤销。`,
      destructive: true,
    })) return;
    try {
      await api.delete(`/api/hosts/${hostId}`);
      toast.success("成功", { description: `主机 ID: ${hostId} 已删除` });
      void fetchHosts();
    } catch (error) {
      notifyRequestError("删除主机失败", "Failed to delete host:", error);
    }
  };

  const requestBatchDelete = async () => {
    if (!await confirm({
      title: '批量删除主机',
      description: `确定要删除选中的 ${selectedHostIds.length} 台主机吗？此操作不可撤销。`,
      confirmText: '删除',
      destructive: true,
    })) return;
    await handleBatchDelete();
  };

  const handleBatchDelete = async () => {
    const ids = [...selectedHostIds];
    if (ids.length === 0) return;
    setIsBatchDeleting(true);
    try {
      const response = await api.delete<{ deleted: number }>('/api/hosts/batch', { data: { ids } });
      toast.success("批量删除完成", { description: `成功删除 ${response.data.deleted} 台主机` });
      setSelectedHostIds([]);
      void fetchHosts();
    } catch (error) {
      notifyRequestError("批量删除失败", "Failed to batch delete hosts:", error);
    } finally {
      setIsBatchDeleting(false);
    }
  };

  const handlePingHost = async (hostId: number) => {
    setHosts(prevHosts => prevHosts.map(h => h.id === hostId ? { ...h, status: 'checking' } : h));
    try {
      const response = await api.get(`/api/hosts/${hostId}/ping`);
      setHosts(prevHosts => prevHosts.map(h => h.id === hostId ? { ...h, status: response.data.status } : h));
      if (response.data.status === 'success') {
        toast.success(`Ping 主机 ${hostId}`, { description: response.data.message });
      } else {
        toast.warning(`Ping 主机 ${hostId}`, { description: response.data.message });
      }
    } catch (error) {
      console.error(`Failed to ping host ${hostId}:`, error);
      setHosts(prevHosts => prevHosts.map(h => h.id === hostId ? { ...h, status: 'failed' } : h));
      toast.error(`Ping 主机 ${hostId} 失败`, {
        description: getApiErrorMessage(error, "检查失败"),
      });
    }
  };

  const handlePingAllHosts = async () => {
    setIsPingingAll(true);
    try {
      const response = await api.post('/api/hosts/check-now');
      const { checked, online, offline, failed } = response.data;
      toast.success("巡检完成", {
        description: `共 ${checked} 台：在线 ${online} / 离线 ${offline} / 异常 ${failed}`,
      });
      await fetchHosts();
    } catch (error) {
      notifyRequestError("巡检失败", "Failed to run patrol:", error);
    } finally {
      setIsPingingAll(false);
    }
  };

  const handleExecuteCommand = async (target: 'selected' | 'all') => {
    if (!command.trim()) {
      toast.error("错误", { description: "请输入要执行的命令" });
      return;
    }
    let targetHostIds: number[] | 'all';
    if (target === 'selected') {
      if (selectedHostIds.length === 0) {
        toast.error("错误", { description: "请在下方表格中选择目标主机" });
        return;
      }
      targetHostIds = selectedHostIds;
    } else {
      targetHostIds = 'all';
    }
    setIsExecutingCommand(true);
    addLog(`[${new Date().toLocaleTimeString()}] 执行命令 '${command}' 于 ${target === 'all' ? '所有主机' : '主机 ' + (Array.isArray(targetHostIds) ? targetHostIds.join(', ') : '')}...`);
    try {
      const response = await api.post('/api/execute', { command: command, hosts: targetHostIds });
      addLog(`[${new Date().toLocaleTimeString()}] 命令执行结果:\n${JSON.stringify(response.data, null, 2)}`);
      toast.success("命令执行成功");
    } catch (error) {
      console.error('Command execution failed:', error);
      const errorMsg = getApiErrorMessage(error);
      addLog(`[${new Date().toLocaleTimeString()}] 命令执行失败: ${errorMsg}`);
      toast.error("命令执行失败", { description: errorMsg });
    } finally {
      setIsExecutingCommand(false);
    }
  };

  const addLog = (message: string) => {
    setCommandLogs(prevLogs => [...prevLogs.slice(-100), message]);
  };

  const handleSelectAllHosts = (checked: boolean | 'indeterminate') => {
    const pageIds = hostTable.pageRows.map(h => h.id);
    if (checked === true) {
      // 只选中当前页：分页后若选中所有筛选结果，批量删除会删掉屏幕上看不见的主机
      setSelectedHostIds(prev => Array.from(new Set([...prev, ...pageIds])));
    }
    else {
      setSelectedHostIds(prev => prev.filter(id => !pageIds.includes(id)));
    }
  };

  const handleHostSelectionChange = (hostId: number, checked: boolean) => {
    setSelectedHostIds(prev =>
      checked ? [...prev, hostId] : prev.filter(id => id !== hostId)
    );
  };

  const openTerminal = (hostId: number) => {
    const terminalWindow = window.open(`/terminal/${hostId}`, `terminal_${hostId}`, 'width=800,height=600');
    if (!terminalWindow) {
      toast.error('无法打开终端', { description: '请允许浏览器打开弹出窗口' });
    }
  };

  const openUploadDialog = (target: 'selected' | 'all') => {
    if (target === 'selected' && selectedHostIds.length === 0) {
      toast.error("错误", { description: "请选择要上传文件的主机" });
      return;
    }
    if (target === 'all' && hosts.length === 0) {
      toast.error("错误", { description: "没有主机可供上传" });
      return;
    }
    setUploadTarget(target);
    setIsUploadDialogOpen(true);
  };

  const handleCleanupAccessLogs = async () => {
    if (!await confirm({
      title: '清理日志',
      description: '确定要清理 3 天前的访问日志和命令日志吗？',
      destructive: true,
    })) return;
    try {
      const response = await api.post('/api/access-logs/cleanup');
      toast.success("成功", { description: response.data.message });
      fetchAccessLogs(accessLogIpFilter, accessLogPathFilter);
    } catch (error) {
      notifyRequestError("清理日志失败", "Failed to cleanup access logs:", error);
    }
  };

  const openPlaybookDialog = (target: 'selected' | 'all') => {
    if (target === 'selected' && selectedHostIds.length === 0) {
      toast.error("错误", { description: "请选择要执行任务的主机" });
      return;
    }
    if (target === 'all' && hosts.length === 0) {
      toast.error("错误", { description: "没有主机可供执行任务" });
      return;
    }
    setPlaybookTarget(target);
    setIsPlaybookDialogOpen(true);
  };

  // 按分组执行：直接选中该组全部主机并打开执行任务弹窗
  const executeOnGroup = (tag: string) => {
    const ids = hosts.filter(h => (h.tag ?? '').trim() === tag).map(h => h.id);
    if (ids.length === 0) {
      toast.error("错误", { description: "该分组下没有主机" });
      return;
    }
    setSelectedHostIds(ids);
    setPlaybookTarget('selected');
    setIsPlaybookDialogOpen(true);
  };

  // 表头复选框只反映当前页的选中情况（与 handleSelectAllHosts 的作用范围保持一致）
  const isAllSelected = hostTable.pageRows.length > 0 && hostTable.pageRows.every(h => selectedHostIds.includes(h.id));
  const isIndeterminate = hostTable.pageRows.some(h => selectedHostIds.includes(h.id)) && !isAllSelected;

  if (isAuthChecking) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="flex flex-col items-center gap-2">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
          <p className="text-sm text-muted-foreground">验证登录状态...</p>
        </div>
      </div>
    );
  }

  return (
    <TooltipProvider>
      <div className="container mx-auto p-4 md:p-6 lg:p-8 space-y-6">
        <header className="flex flex-col sm:flex-row justify-between items-center gap-4">
          <div>
            <h1 className="flex items-center gap-2.5 text-2xl font-semibold sm:text-[26px]">
              <span className="h-[18px] w-[3px] rounded-sm bg-primary" />
              Ansible 面板
            </h1>
            <p className="mt-1.5 pl-[13px] text-xs text-muted-foreground">添加、编辑和管理 Ansible 主机，执行命令与运维任务。</p>
          </div>
          <Sheet open={isLogSheetOpen} onOpenChange={setIsLogSheetOpen}>
            <SheetTrigger asChild>
              <Button variant="outline" onClick={() => { fetchAccessLogs(); fetchAccessLogUsers(); }}> <ReaderIcon className="mr-2 h-4 w-4" /> 访问日志</Button>
            </SheetTrigger>
            <SheetContent className="w-full sm:max-w-3xl">
              <SheetHeader>
                <SheetTitle>系统访问日志</SheetTitle>
                <SheetDescription>查看最近的系统访问记录。</SheetDescription>
              </SheetHeader>
              <div className="grid gap-4 py-4">
                <div className="flex flex-col sm:flex-row gap-2 items-center">
                  <Input
                    placeholder="搜索 IP 地址"
                    value={accessLogIpFilter}
                    onChange={(e) => setAccessLogIpFilter(e.target.value)}
                    className="flex-1"
                  />
                  <Input
                    placeholder="搜索路径"
                    value={accessLogPathFilter}
                    onChange={(e) => setAccessLogPathFilter(e.target.value)}
                    className="flex-1"
                  />
                  <select
                    aria-label="按操作人筛选"
                    className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                    value={accessLogUserFilter}
                    onChange={(e) => setAccessLogUserFilter(e.target.value)}
                  >
                    <option value="">全部操作人</option>
                    {accessLogUsers.map(name => <option key={name} value={name}>{name}</option>)}
                  </select>
                  <div className="flex gap-2 w-full sm:w-auto">
                    <Button className="flex-1 sm:flex-none" onClick={() => fetchAccessLogs(accessLogIpFilter, accessLogPathFilter, accessLogUserFilter)} disabled={isLoadingAccessLogs}>
                      {isLoadingAccessLogs ? '搜索中...' : '搜索'}
                    </Button>
                    <Button className="flex-1 sm:flex-none" variant="outline" onClick={() => { setAccessLogIpFilter(''); setAccessLogPathFilter(''); setAccessLogUserFilter(''); fetchAccessLogs(); }}>重置</Button>
                  </div>
                </div>
                <div className="max-h-[60vh] overflow-y-auto border rounded-md">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-muted/60 hover:bg-muted/60">
                        <SortableHead sortKey="time" activeKey={accessLogTable.sortKey} dir={accessLogTable.sortDir} onSort={accessLogTable.toggleSort}>时间</SortableHead>
                        <SortableHead sortKey="username" activeKey={accessLogTable.sortKey} dir={accessLogTable.sortDir} onSort={accessLogTable.toggleSort}>操作人</SortableHead>
                        <SortableHead sortKey="ip" activeKey={accessLogTable.sortKey} dir={accessLogTable.sortDir} onSort={accessLogTable.toggleSort}>IP 地址</SortableHead>
                        <SortableHead sortKey="method" activeKey={accessLogTable.sortKey} dir={accessLogTable.sortDir} onSort={accessLogTable.toggleSort}>请求</SortableHead>
                        <SortableHead sortKey="path" activeKey={accessLogTable.sortKey} dir={accessLogTable.sortDir} onSort={accessLogTable.toggleSort}>路径</SortableHead>
                        <SortableHead sortKey="status_code" activeKey={accessLogTable.sortKey} dir={accessLogTable.sortDir} onSort={accessLogTable.toggleSort}>状态码</SortableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {isLoadingAccessLogs ? (
                        <TableRow><TableCell colSpan={6} className="text-center py-4">加载中...</TableCell></TableRow>
                      ) : accessLogs.length > 0 ? (
                        accessLogTable.pageRows.map((log) => (
                          <TableRow key={log.id}>
                            <TableCell className="text-xs sm:text-sm">{new Date(log.access_time).toLocaleString()}</TableCell>
                            <TableCell className="text-xs sm:text-sm">{log.username || '-'}</TableCell>
                            <TableCell className="text-xs sm:text-sm">{log.ip_address}</TableCell>
                            <TableCell className="text-xs text-muted-foreground">{log.method || '-'}</TableCell>
                            <TableCell className="text-xs sm:text-sm break-all">{log.path}</TableCell>
                            <TableCell className={`text-xs sm:text-sm ${log.status_code >= 400 ? 'text-red-500 dark:text-red-400' : 'text-green-600 dark:text-emerald-400'}`}>{log.status_code}</TableCell>
                          </TableRow>
                        ))
                      ) : (
                        <TableRow><TableCell colSpan={6} className="text-center py-4">无访问日志</TableCell></TableRow>
                      )}
                    </TableBody>
                  </Table>
                </div>
                <div className="mt-2">
                  <TablePagination
                    page={accessLogTable.page}
                    pageCount={accessLogTable.pageCount}
                    pageSize={accessLogTable.pageSize}
                    total={accessLogTable.total}
                    onPageChange={accessLogTable.setPage}
                    onPageSizeChange={accessLogTable.setPageSize}
                  />
                </div>
              </div>
              <SheetFooter>
                {isAdmin && (
                  <Button variant="outline" onClick={handleCleanupAccessLogs} className="text-black dark:text-white">清理3天前日志</Button>
                )}
                <SheetClose asChild>
                  <Button variant="outline">关闭</Button>
                </SheetClose>
              </SheetFooter>
            </SheetContent>
          </Sheet>
        </header>

        <div className="space-y-2">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <Card className="rounded-md">
              <CardContent className="p-4">
                <div className="text-xs text-muted-foreground">主机总数</div>
                <div className="mt-1 text-2xl font-semibold">{statusCounts.total}</div>
              </CardContent>
            </Card>
            <Card className="rounded-md">
              <CardContent className="p-4">
                <div className="text-xs text-emerald-600 dark:text-emerald-400">在线</div>
                <div className="mt-1 text-2xl font-semibold text-emerald-600 dark:text-emerald-400">{statusCounts.online}</div>
              </CardContent>
            </Card>
            <Card className="rounded-md">
              <CardContent className="p-4">
                <div className="text-xs text-red-600 dark:text-red-400">离线</div>
                <div className="mt-1 text-2xl font-semibold text-red-600 dark:text-red-400">{statusCounts.offline}</div>
              </CardContent>
            </Card>
            <Card className="rounded-md">
              <CardContent className="p-4">
                <div className="text-xs text-orange-600 dark:text-orange-400">异常</div>
                <div className="mt-1 text-2xl font-semibold text-orange-600 dark:text-orange-400">{statusCounts.failed}</div>
              </CardContent>
            </Card>
            <Card className="rounded-md">
              <CardContent className="p-4">
                <div className="text-xs text-muted-foreground">未检查</div>
                <div className="mt-1 text-2xl font-semibold text-muted-foreground">{statusCounts.unchecked}</div>
              </CardContent>
            </Card>
          </div>
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{lastCheckedAt ? `最近巡检：${lastCheckedAt}` : '尚未巡检，可点击「立即巡检」或等待后台定时巡检'}</span>
            <button type="button" onClick={() => void fetchHosts(true)} className="underline hover:text-foreground">刷新状态</button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card className="rounded-md lg:col-span-2">
            <CardHeader className="border-b pb-4">
              <CardTitle className="flex items-center gap-2 text-base">
                <span className="h-3.5 w-[3px] rounded-sm bg-primary" />
                主机管理
              </CardTitle>
              <CardDescription>添加、编辑和管理您的 Ansible 主机。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="搜索备注、地址、用户名或分组..."
                    value={hostSearch}
                    onChange={(e) => setHostSearch(e.target.value)}
                    className="pl-9"
                  />
                  {(hostSearch || hostTagFilter) && (
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">
                      找到 {filteredHosts.length} 台
                    </span>
                  )}
                </div>
                <select
                  value={hostTagFilter}
                  onChange={(e) => setHostTagFilter(e.target.value)}
                  className="h-10 rounded-md border border-input bg-background px-3 text-sm sm:w-[150px]"
                  aria-label="按分组筛选"
                >
                  <option value="">全部分组</option>
                  {availableTags.map(tag => <option key={tag} value={tag}>{tag}</option>)}
                </select>
                {hostTagFilter && isAdmin && (
                  <Button variant="outline" onClick={() => executeOnGroup(hostTagFilter)} className="shrink-0">
                    <PlayIcon className="mr-2 h-4 w-4" /> 执行本组 ({hosts.filter(h => (h.tag ?? '').trim() === hostTagFilter).length})
                  </Button>
                )}
              </div>
              <div className="flex flex-col sm:flex-row justify-between items-center gap-2 mb-2">
                <div className="flex items-center gap-2">
                  {isAdmin && (
                  <Dialog open={isBatchAddOpen} onOpenChange={setIsBatchAddOpen}>
                    <DialogTrigger asChild>
                      <Button><PlusCircledIcon className="mr-2 h-4 w-4" /> 批量添加主机</Button>
                    </DialogTrigger>
                    <DialogContent className="sm:max-w-[600px] dialog-content-scroll-hide">
                      <DialogHeader>
                        <DialogTitle>批量添加主机</DialogTitle>
                        <DialogDescription>
                          每行输入一台主机信息，格式：
                          {useKeyAuth
                            ? "备注 地址 用户 端口"
                            : "备注 地址 用户 端口 SSH密码"}
                          。例如：<br />
                          <code>
                            {useKeyAuth
                              ? "us 192.168.1.1 root 22"
                              : "us 192.168.1.2 root 22 yourpassword"}
                          </code>
                        </DialogDescription>
                      </DialogHeader>
                      <div className="grid gap-4 py-4">
                        {useKeyAuth && (
                          <div className="grid gap-2">
                            <Label htmlFor="batch-key-path">SSH 私钥路径（可选，留空使用服务端全局配置）</Label>
                            <Input id="batch-key-path" placeholder="/root/.ssh/id_ed25519" value={batchKeyPath} onChange={(e) => setBatchKeyPath(e.target.value)} />
                          </div>
                        )}
                        <div className="grid gap-2">
                          <Label htmlFor="batch-tag">分组（可选，本批次统一设置）</Label>
                          <Input id="batch-tag" list="batch-tag-options" placeholder="如：生产环境、测试环境" value={batchTag} onChange={(e) => setBatchTag(e.target.value)} />
                          <datalist id="batch-tag-options">
                            {availableTags.map(tag => <option key={tag} value={tag} />)}
                          </datalist>
                        </div>
                        <Textarea
                          placeholder="需遵循示例格式输入"
                          rows={5}
                          value={batchInput}
                          onChange={(e) => setBatchInput(e.target.value)}
                          className="placeholder:opacity-40 batch-input-textarea"
                        />
                      </div>
                      <DialogFooter>
                        <DialogClose asChild>
                          <Button type="button" variant="outline">取消</Button>
                        </DialogClose>
                        <Button type="button" onClick={handleAddHosts} disabled={isAddingHost}>
                          {isAddingHost ? '添加中...' : '确认添加'}
                        </Button>
                      </DialogFooter>
                    </DialogContent>
                  </Dialog>
                  )}
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div className="flex items-center space-x-2">
                        <Switch id="key-auth-switch" checked={useKeyAuth} onCheckedChange={setUseKeyAuth} disabled={!isAdmin} />
                        <Label htmlFor="key-auth-switch" className="cursor-pointer">
                          {useKeyAuth ? '密钥认证模式' : '密码认证模式'}
                        </Label>
                      </div>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p>{useKeyAuth ? '新添加的主机将使用 /root/.ssh/id_ed25519 路径的密钥认证' : '新添加的主机将使用密码认证'}</p>
                    </TooltipContent>
                  </Tooltip>
                </div>
                <div className="flex gap-2">
                  {isAdmin && (
                    <>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button variant="outline" size="sm"
                            disabled={selectedHostIds.length === 0}
                            onClick={() => openPlaybookDialog('selected')}>
                            <PlayIcon className="mr-2 h-4 w-4" /> 执行任务
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent><p>在选中的主机上执行自定义任务</p></TooltipContent>
                      </Tooltip>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button variant="outline" size="sm"
                            disabled={selectedHostIds.length === 0}
                            onClick={() => openUploadDialog('selected')}>
                            <UploadIcon className="mr-2 h-4 w-4" /> 上传文件
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent><p>上传文件到选中的主机</p></TooltipContent>
                      </Tooltip>
                    </>
                  )}
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button variant="outline" size="sm" onClick={() => void handlePingAllHosts()} disabled={isLoadingHosts || isPingingAll || !isAdmin}>
                        <ReloadIcon className={`mr-2 h-4 w-4 ${isPingingAll ? 'animate-spin' : ''}`} /> {isPingingAll ? '巡检中...' : '立即巡检'}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent><p>立即巡检所有主机并更新状态看板</p></TooltipContent>
                  </Tooltip>
                  {isAdmin && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button variant="destructive" size="sm"
                        disabled={selectedHostIds.length === 0 || isBatchDeleting}
                        onClick={() => void requestBatchDelete()}>
                        <Trash2 className="mr-2 h-4 w-4" /> {isBatchDeleting ? '删除中...' : `批量删除 (${selectedHostIds.length})`}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent><p>删除所有已选中的主机</p></TooltipContent>
                  </Tooltip>
                  )}
                </div>
              </div>

              <div className="border rounded-md overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/60 hover:bg-muted/60">
                      <TableHead className="w-[50px] px-2 sm:px-4">
                        <Checkbox
                          checked={isIndeterminate ? 'indeterminate' : isAllSelected}
                          onCheckedChange={handleSelectAllHosts}
                          aria-label="Select all hosts"
                        />
                      </TableHead>
                      <SortableHead sortKey="comment" activeKey={hostTable.sortKey} dir={hostTable.sortDir} onSort={hostTable.toggleSort}>备注</SortableHead>
                      <SortableHead sortKey="tag" activeKey={hostTable.sortKey} dir={hostTable.sortDir} onSort={hostTable.toggleSort}>分组</SortableHead>
                      <SortableHead sortKey="address" activeKey={hostTable.sortKey} dir={hostTable.sortDir} onSort={hostTable.toggleSort}>地址</SortableHead>
                      <SortableHead sortKey="username" className="hidden md:table-cell" activeKey={hostTable.sortKey} dir={hostTable.sortDir} onSort={hostTable.toggleSort}>用户名</SortableHead>
                      <SortableHead sortKey="port" className="hidden lg:table-cell" activeKey={hostTable.sortKey} dir={hostTable.sortDir} onSort={hostTable.toggleSort}>端口</SortableHead>
                      <SortableHead sortKey="status" activeKey={hostTable.sortKey} dir={hostTable.sortDir} onSort={hostTable.toggleSort}>状态</SortableHead>
                      <TableHead className="text-right">操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {isLoadingHosts ? (
                      <TableRow><TableCell colSpan={8} className="text-center py-4">加载中...</TableCell></TableRow>
                    ) : filteredHosts.length > 0 ? (
                      hostTable.pageRows.map((host) => (
                        <TableRow key={host.id}>
                          <TableCell className="px-2 sm:px-4">
                            <Checkbox
                              checked={selectedHostIds.includes(host.id)}
                              onCheckedChange={(checked) => handleHostSelectionChange(host.id, !!checked)}
                              aria-label={`Select host ${host.id}`}
                            />
                          </TableCell>
                          <TableCell className="font-medium">{host.comment}</TableCell>
                          <TableCell>
                            {(host.tag ?? '').trim() ? (
                              <span className="inline-flex items-center rounded bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                                {(host.tag ?? '').trim()}
                              </span>
                            ) : (
                              <span className="text-xs text-muted-foreground">—</span>
                            )}
                          </TableCell>
                          <TableCell>{host.address}</TableCell>
                          <TableCell className="hidden md:table-cell">{host.username}</TableCell>
                          <TableCell className="hidden lg:table-cell">{host.port}</TableCell>
                          <TableCell>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span>
                                  {host.status === 'checking' && (
                                    <span className="inline-flex items-center gap-1 rounded bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                                      <ReloadIcon className="h-3 w-3 animate-spin" />检查中
                                    </span>
                                  )}
                                  {host.status === 'success' && (
                                    <span className="inline-flex items-center gap-1 rounded bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-400">
                                      <CheckCircledIcon className="h-3 w-3" />在线
                                    </span>
                                  )}
                                  {host.status === 'unreachable' && (
                                    <span className="inline-flex items-center gap-1 rounded bg-red-50 px-2 py-0.5 text-xs font-medium text-red-600 dark:bg-red-500/15 dark:text-red-400">
                                      <CrossCircledIcon className="h-3 w-3" />离线
                                    </span>
                                  )}
                                  {host.status === 'failed' && (
                                    <span className="inline-flex items-center gap-1 rounded bg-orange-50 px-2 py-0.5 text-xs font-medium text-orange-600 dark:bg-orange-500/15 dark:text-orange-400">
                                      <InfoCircledIcon className="h-3 w-3" />异常
                                    </span>
                                  )}
                                  {!host.status && <span className="text-xs text-muted-foreground">未检查</span>}
                                </span>
                              </TooltipTrigger>
                              <TooltipContent>
                                {host.status === 'checking' && <p>检查中...</p>}
                                {host.status === 'success' && <p>连接成功</p>}
                                {host.status === 'unreachable' && <p>无法连接</p>}
                                {host.status === 'failed' && <p>检查失败</p>}
                                {!host.status && <p>未检查</p>}
                              </TooltipContent>
                            </Tooltip>
                          </TableCell>
                          <TableCell className="text-right space-x-0.5 sm:space-x-1">
                            {isAdmin && (
                              <>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button variant="ghost" size="icon" onClick={() => handlePingHost(host.id)} disabled={host.status === 'checking'}>
                                  <ReloadIcon className="h-4 w-4" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent><p>Ping 主机</p></TooltipContent>
                            </Tooltip>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button variant="ghost" size="icon" onClick={() => openTerminal(host.id)}>
                                  <TerminalIcon className="h-4 w-4" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent><p>打开终端</p></TooltipContent>
                            </Tooltip>
                              </>
                            )}
                            {isAdmin && (
                            <Dialog open={editingHost?.id === host.id} onOpenChange={(isOpen) => !isOpen && setEditingHost(null)}>
                              <DialogTrigger asChild>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button variant="ghost" size="icon" onClick={() => handleEditHost(host)}>
                                      <Pencil1Icon className="h-4 w-4" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent><p>编辑主机</p></TooltipContent>
                                </Tooltip>
                              </DialogTrigger>
                              <DialogContent className="sm:max-w-[425px]">
                                <DialogHeader>
                                  <DialogTitle>编辑主机: {editingHost?.comment}</DialogTitle>
                                  <DialogDescription>修改主机信息。留空密码字段则不更新密码。</DialogDescription>
                                </DialogHeader>
                                {editingHost && (
                                  <div className="grid gap-4 py-4">
                                    <div className="grid grid-cols-4 items-center gap-4">
                                      <Label htmlFor="edit-comment" className="text-right">备注</Label>
                                      <Input id="edit-comment" value={editingHost.comment} onChange={(e) => setEditingHost({ ...editingHost, comment: e.target.value })} className="col-span-3" />
                                    </div>
                                    <div className="grid grid-cols-4 items-center gap-4">
                                      <Label htmlFor="edit-address" className="text-right">地址</Label>
                                      <Input id="edit-address" value={editingHost.address} onChange={(e) => setEditingHost({ ...editingHost, address: e.target.value })} className="col-span-3" />
                                    </div>
                                    <div className="grid grid-cols-4 items-center gap-4">
                                      <Label htmlFor="edit-username" className="text-right">用户名</Label>
                                      <Input id="edit-username" value={editingHost.username} onChange={(e) => setEditingHost({ ...editingHost, username: e.target.value })} className="col-span-3" />
                                    </div>
                                    <div className="grid grid-cols-4 items-center gap-4">
                                      <Label htmlFor="edit-port" className="text-right">端口</Label>
                                      <Input id="edit-port" type="number" value={editingHost.port} onChange={(e) => setEditingHost({ ...editingHost, port: parseInt(e.target.value, 10) || 22 })} className="col-span-3" />
                                    </div>
                                    <div className="grid grid-cols-4 items-center gap-4">
                                      <Label htmlFor="edit-tag" className="text-right">分组</Label>
                                      <div className="col-span-3">
                                        <Input
                                          id="edit-tag"
                                          list="host-tag-options"
                                          placeholder="如：生产环境、测试环境（留空则无分组）"
                                          value={editingHost.tag ?? ''}
                                          onChange={(e) => setEditingHost({ ...editingHost, tag: e.target.value })}
                                        />
                                        <datalist id="host-tag-options">
                                          {availableTags.map(tag => <option key={tag} value={tag} />)}
                                        </datalist>
                                      </div>
                                    </div>
                                    <div className="grid grid-cols-4 items-center gap-4">
                                      <Label htmlFor="edit-auth-method" className="text-right">认证方式</Label>
                                      <div className="col-span-3 flex items-center space-x-2">
                                        <Switch
                                          id="edit-auth-method"
                                          checked={editingHost.auth_method === 'key'}
                                          onCheckedChange={(checked) => setEditingHost({ ...editingHost, auth_method: checked ? 'key' : 'password' })}
                                        />
                                        <Label htmlFor="edit-auth-method">{editingHost.auth_method === 'key' ? '密钥认证' : '密码认证'}</Label>
                                      </div>
                                    </div>
                                    {editingHost.auth_method === 'key' && (
                                      <div className="grid grid-cols-4 items-center gap-4">
                                        <Label htmlFor="edit-key-path" className="text-right">密钥路径</Label>
                                        <Input id="edit-key-path" placeholder="留空则使用全局配置" value={editingHost.private_key_path || ''} onChange={(e) => setEditingHost({ ...editingHost, private_key_path: e.target.value })} className="col-span-3" />
                                      </div>
                                    )}
                                    {editingHost.auth_method === 'password' && (
                                      <div className="grid grid-cols-4 items-center gap-4">
                                        <Label htmlFor="edit-password" className="text-right">密码</Label>
                                        <Input id="edit-password" type="password" placeholder="留空则不修改" onChange={(e) => setEditingHost({ ...editingHost, password: e.target.value })} className="col-span-3" />
                                      </div>
                                    )}
                                  </div>
                                )}
                                <DialogFooter>
                                  <DialogClose asChild>
                                    <Button type="button" variant="outline">取消</Button>
                                  </DialogClose>
                                  <Button type="button" onClick={() => editingHost && handleSaveEdit(editingHost)} disabled={isEditingHost}>
                                    {isEditingHost ? '保存中...' : '保存更改'}
                                  </Button>
                                </DialogFooter>
                              </DialogContent>
                            </Dialog>
                            )}
                            {isAdmin && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button variant="ghost" size="icon" onClick={() => handleDeleteHost(host.id)} className="text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300">
                                  <TrashIcon className="h-4 w-4" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent><p>删除主机</p></TooltipContent>
                            </Tooltip>
                            )}
                          </TableCell>
                        </TableRow>
                      ))
                    ) : (
                      <TableRow><TableCell colSpan={8} className="text-center py-4">
                        {hostSearch.trim() || hostTagFilter
                          ? `没有找到匹配的主机${hostTagFilter ? `（分组：${hostTagFilter}）` : ''}`
                          : '没有找到主机'}
                      </TableCell></TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
              <TablePagination
                page={hostTable.page}
                pageCount={hostTable.pageCount}
                pageSize={hostTable.pageSize}
                total={hostTable.total}
                onPageChange={hostTable.setPage}
                onPageSizeChange={hostTable.setPageSize}
              />
            </CardContent>
          </Card>

          <Card className="rounded-md lg:col-span-1">
            <CardHeader className="border-b pb-4">
              <CardTitle className="flex items-center gap-2 text-base">
                <span className="h-3.5 w-[3px] rounded-sm bg-primary" />
                命令区域
              </CardTitle>
              <CardDescription>执行 shell 命令。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 flex flex-col h-full">
              <div className="grid gap-2">
                <Label htmlFor="commandInput">输入命令</Label>
                <Textarea
                  id="commandInput"
                  placeholder="例如：ls /home"
                  rows={3} // Reduced rows
                  value={command}
                  onChange={(e) => setCommand(e.target.value)}
                  className="resize-y min-h-[80px] placeholder:opacity-40"
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button className="flex-1 sm:flex-none" onClick={() => handleExecuteCommand('selected')} disabled={!isAdmin || isExecutingCommand || selectedHostIds.length === 0}>
                  <PlayIcon className="mr-2 h-4 w-4" /> 发送到选中 ({selectedHostIds.length})
                </Button>
                <Button className="flex-1 sm:flex-none" onClick={() => handleExecuteCommand('all')} disabled={!isAdmin || isExecutingCommand || hosts.length === 0}>
                  <PlayIcon className="mr-2 h-4 w-4" /> 发送到所有 ({hosts.length})
                </Button>
                {!isAdmin && (
                  <span className="self-center text-xs text-muted-foreground">只读账号无法执行命令</span>
                )}
              </div>

              <div className="flex flex-col flex-grow min-h-[200px]">
                <h3 className="text-lg font-semibold mb-2">执行日志</h3>
                <div className="border rounded-md p-3 flex-grow overflow-y-auto bg-muted/90 dark:bg-muted/90 text-sm font-mono whitespace-pre-wrap">
                  {commandLogs.length > 0 ? commandLogs.join('\n') : <span className="text-muted-foreground">暂无日志</span>}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <Dialog open={isUploadDialogOpen} onOpenChange={setIsUploadDialogOpen}>
          <DialogContent className="sm:max-w-[525px]">
            <DialogHeader>
              <DialogTitle>文件上传</DialogTitle>
              <DialogDescription>
                选择文件并指定远程路径，然后上传到 {uploadTarget === 'all' ? '所有主机' : '选定主机'}。
              </DialogDescription>
            </DialogHeader>
            {uploadTarget && (
              <FileUpload
                targetHostIds={uploadTarget === 'all' ? 'all' : selectedHostIds}
                onClose={() => setIsUploadDialogOpen(false)}
              />
            )}
          </DialogContent>
        </Dialog>

        <Dialog open={isPlaybookDialogOpen} onOpenChange={setIsPlaybookDialogOpen}>
          <DialogContent className="sm:max-w-[700px] max-h-[90vh] overflow-y-auto dialog-content-scroll-hide">
            <DialogHeader>
              <DialogTitle>执行Ansible Playbook</DialogTitle>
              <DialogDescription>
                在 {playbookTarget === 'all' ? '所有主机' : '选定主机'} 上执行自定义Playbook。
              </DialogDescription>
            </DialogHeader>

            {playbookTarget && (
              <PlaybookExecutor
                targetHostIds={playbookTarget === 'all' ? 'all' : selectedHostIds}
                onClose={() => setIsPlaybookDialogOpen(false)}
              />
            )}
          </DialogContent>
        </Dialog>

        <div className="text-center mt-6 mb-2">
          <a
            href="https://github.com/sky22333/ansible-ui"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
            title="GitHub仓库"
          >
            <Github size={16} />
          </a>
        </div>
      </div>
    </TooltipProvider>
  );
}

export default MainPage;


