import { useCallback, useEffect, useState } from 'react';
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import api from '@/services/api';
import { Search, RotateCcw } from 'lucide-react';
import { getApiErrorMessage } from '@/utils/http';
import { SortableHead, TablePagination } from '@/components/table-controls';
import type { SortDir } from '@/hooks/useTableControls';

interface CommandLog {
  id: number;
  host_id: number | null;
  command: string;
  output: string | null;
  status: string;
  executed_at: string;
  playbook_id?: number | null;
  playbook_name?: string | null;
  comment: string | null;
  address: string | null;
}

interface HostOption {
  id: number;
  comment: string;
  address: string;
}

const PAGE_SIZE = 20;

const statusMeta: Record<string, { label: string; className: string }> = {
  success: { label: '成功', className: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-400' },
  failed: { label: '失败', className: 'bg-red-50 text-red-600 dark:bg-red-500/15 dark:text-red-400' },
  unreachable: { label: '不可达', className: 'bg-orange-50 text-orange-600 dark:bg-orange-500/15 dark:text-orange-400' },
};

function typeMeta(command: string) {
  if (command === 'ping') return { label: '连通性巡检', className: 'bg-slate-100 text-slate-600 dark:bg-slate-700/50 dark:text-slate-300' };
  if (command === 'Custom Playbook Execution') return { label: 'Playbook', className: 'bg-primary/10 text-primary' };
  return { label: 'Shell 命令', className: 'bg-blue-50 text-blue-600 dark:bg-blue-500/15 dark:text-blue-400' };
}

function formatOutput(raw: string | null) {
  if (!raw) return '（无输出）';
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

function HistoryPage() {
  const [logs, setLogs] = useState<CommandLog[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [hosts, setHosts] = useState<HostOption[]>([]);
  const [keyword, setKeyword] = useState('');
  const [hostFilter, setHostFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(PAGE_SIZE);
  // 排序在后端完成（服务端分页），默认按时间倒序
  const [sortKey, setSortKey] = useState<string | null>('executed_at');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [detail, setDetail] = useState<CommandLog | null>(null);

  useEffect(() => {
    void api.get<HostOption[]>('/api/hosts')
      .then(res => setHosts(res.data))
      .catch(() => { /* 主机下拉加载失败不影响日志查询 */ });
  }, []);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get<{ items: CommandLog[]; total: number }>('/api/logs', {
        params: {
          limit: pageSize,
          offset: page * pageSize,
          host_id: hostFilter || undefined,
          status: statusFilter || undefined,
          date_from: dateFrom || undefined,
          date_to: dateTo || undefined,
          keyword: keyword.trim() || undefined,
          sort: sortKey ?? undefined,
          order: sortDir,
        },
      });
      setLogs(res.data.items);
      setTotal(res.data.total);
    } catch (error) {
      toast.error('获取执行历史失败', { description: getApiErrorMessage(error) });
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, sortKey, sortDir, hostFilter, statusFilter, dateFrom, dateTo, keyword]);

  useEffect(() => { void fetchLogs(); }, [fetchLogs]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const resetPage = () => setPage(0);
  const clearFilters = () => {
    setKeyword(''); setHostFilter(''); setStatusFilter(''); setDateFrom(''); setDateTo(''); setPage(0);
  };

  // 点击表头：同列切换方向，换列回到升序；排序变化后回到第一页
  const toggleSort = (key: string) => {
    if (key === sortKey) {
      setSortDir(dir => (dir === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
    setPage(0);
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setPage(0);
  };

  return (
    <div className="container mx-auto space-y-6 p-4 md:p-6 lg:p-8">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <span className="h-5 w-[3px] rounded-sm bg-primary" />
          任务执行历史
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">统一查看 Shell 命令、连通性巡检与 Playbook 的执行记录。</p>
      </div>

      <Card className="rounded-md">
        <CardHeader className="border-b pb-4">
          <CardTitle className="flex items-center gap-2 text-base">
            <span className="h-3.5 w-[3px] rounded-sm bg-primary" />
            筛选
          </CardTitle>
          <CardDescription>按主机、状态、时间范围或关键词过滤。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 pt-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="搜索命令/输出/主机"
                value={keyword}
                onChange={(e) => { setKeyword(e.target.value); resetPage(); }}
                className="pl-9"
              />
            </div>
            <select
              value={hostFilter}
              onChange={(e) => { setHostFilter(e.target.value); resetPage(); }}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
              aria-label="按主机筛选"
            >
              <option value="">全部主机</option>
              {hosts.map(h => <option key={h.id} value={h.id}>{h.comment} ({h.address})</option>)}
            </select>
            <select
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value); resetPage(); }}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
              aria-label="按状态筛选"
            >
              <option value="">全部状态</option>
              <option value="success">成功</option>
              <option value="failed">失败</option>
              <option value="unreachable">不可达</option>
            </select>
            <div className="flex items-center gap-2">
              <Label htmlFor="date-from" className="shrink-0 text-xs text-muted-foreground">起</Label>
              <Input id="date-from" type="date" value={dateFrom}
                onChange={(e) => { setDateFrom(e.target.value); resetPage(); }} />
            </div>
            <div className="flex items-center gap-2">
              <Label htmlFor="date-to" className="shrink-0 text-xs text-muted-foreground">止</Label>
              <Input id="date-to" type="date" value={dateTo}
                onChange={(e) => { setDateTo(e.target.value); resetPage(); }} />
            </div>
          </div>
          <div className="flex items-center justify-between">
            <Button variant="outline" size="sm" onClick={clearFilters}>
              <RotateCcw className="mr-2 h-4 w-4" /> 重置筛选
            </Button>
            <span className="text-xs text-muted-foreground">共 {total} 条记录</span>
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-md">
        <CardHeader className="border-b pb-4">
          <CardTitle className="flex items-center gap-2 text-base">
            <span className="h-3.5 w-[3px] rounded-sm bg-primary" />
            执行记录
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          <div className="border rounded-md overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/60 hover:bg-muted/60">
                  <SortableHead sortKey="executed_at" className="whitespace-nowrap" activeKey={sortKey} dir={sortDir} onSort={toggleSort}>时间</SortableHead>
                  <SortableHead sortKey="host" activeKey={sortKey} dir={sortDir} onSort={toggleSort}>主机</SortableHead>
                  <SortableHead sortKey="type" activeKey={sortKey} dir={sortDir} onSort={toggleSort}>类型</SortableHead>
                  <SortableHead sortKey="command" activeKey={sortKey} dir={sortDir} onSort={toggleSort}>命令 / 任务</SortableHead>
                  <SortableHead sortKey="status" activeKey={sortKey} dir={sortDir} onSort={toggleSort}>状态</SortableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow><TableCell colSpan={6} className="text-center py-8">加载中...</TableCell></TableRow>
                ) : logs.length > 0 ? logs.map(log => {
                  const t = typeMeta(log.command);
                  const s = statusMeta[log.status] ?? { label: log.status, className: 'bg-muted text-muted-foreground' };
                  return (
                    <TableRow key={log.id}>
                      <TableCell className="whitespace-nowrap text-xs">{log.executed_at}</TableCell>
                      <TableCell>
                        {log.comment ? (
                          <div className="text-sm">
                            <div className="font-medium">{log.comment}</div>
                            <div className="text-xs text-muted-foreground">{log.address}</div>
                          </div>
                        ) : (
                          <span className="text-xs text-muted-foreground">全部主机 / 已删除</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <span className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${t.className}`}>{t.label}</span>
                      </TableCell>
                      <TableCell className="max-w-[260px] truncate font-mono text-xs" title={log.playbook_name ? `Playbook: ${log.playbook_name}` : log.command}>
                        {log.playbook_name ? `Playbook: ${log.playbook_name}` : log.command}
                      </TableCell>
                      <TableCell>
                        <span className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${s.className}`}>{s.label}</span>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button variant="ghost" size="sm" onClick={() => setDetail(log)}>详情</Button>
                      </TableCell>
                    </TableRow>
                  );
                }) : (
                  <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">没有符合条件的执行记录</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </div>
          <div className="mt-4">
            <TablePagination
              page={page + 1}
              pageCount={totalPages}
              pageSize={pageSize}
              total={total}
              onPageChange={(next) => setPage(next - 1)}
              onPageSizeChange={handlePageSizeChange}
            />
          </div>
        </CardContent>
      </Card>

      <Dialog open={!!detail} onOpenChange={(open) => !open && setDetail(null)}>
        <DialogContent className="sm:max-w-[700px] max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>执行详情 #{detail?.id}</DialogTitle>
            <DialogDescription>
              {detail?.executed_at} · {detail?.comment ? `${detail.comment} (${detail.address})` : '全部主机 / 已删除'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            {detail?.playbook_name && (
              <div>
                <div className="mb-1 text-xs font-medium text-muted-foreground">关联 Playbook</div>
                <div className="inline-flex rounded bg-primary/10 px-3 py-1.5 text-sm font-medium text-primary">
                  {detail.playbook_name}
                </div>
              </div>
            )}
            <div>
              <div className="mb-1 text-xs font-medium text-muted-foreground">命令 / 任务</div>
              <pre className="rounded bg-muted p-3 font-mono text-xs whitespace-pre-wrap break-all">{detail?.command}</pre>
            </div>
            <div>
              <div className="mb-1 text-xs font-medium text-muted-foreground">执行输出</div>
              <pre className="max-h-[45vh] overflow-auto rounded bg-muted p-3 font-mono text-xs whitespace-pre-wrap break-all">{formatOutput(detail?.output ?? null)}</pre>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default HistoryPage;
