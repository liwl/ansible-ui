import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react';
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import api from '@/services/api';
import { getApiErrorMessage } from '@/utils/http';
import { confirm } from '@/components/ConfirmDialog';
import { useAuth } from '@/contexts/use-auth';
import {
  Folder, File as FileIcon, Upload, FolderPlus, FilePlus, RefreshCw,
  Download, Pencil, Trash2, ChevronRight, ArrowUp,
} from 'lucide-react';
import { useTableControls } from '@/hooks/useTableControls';
import { SortableHead, TablePagination } from '@/components/table-controls';

interface SftpEntry {
  name: string;
  type: 'file' | 'directory';
  size: number;
  mtime: number;
}

interface HostOption {
  id: number;
  comment: string;
  address: string;
}

const joinPath = (base: string, name: string) => {
  if (!base || base === '/') return `/${name}`;
  return `${base.replace(/\/+$/, '')}/${name}`;
};

const parentPath = (p: string) => {
  const cleaned = p.replace(/\/+$/, '') || '/';
  if (cleaned === '/') return '/';
  const idx = cleaned.lastIndexOf('/');
  return idx <= 0 ? '/' : cleaned.slice(0, idx);
};

const formatSize = (n: number) => {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
};

function FilesPage() {
  const { isAdmin } = useAuth();
  const [hosts, setHosts] = useState<HostOption[]>([]);
  const [hostId, setHostId] = useState<number | ''>('');
  const [path, setPath] = useState('/');
  const [pathInput, setPathInput] = useState('/');
  const [entries, setEntries] = useState<SftpEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [mkdirOpen, setMkdirOpen] = useState(false);
  const [mkdirName, setMkdirName] = useState('');
  const [touchOpen, setTouchOpen] = useState(false);
  const [touchName, setTouchName] = useState('');
  const [renameEntry, setRenameEntry] = useState<SftpEntry | null>(null);
  const [renameName, setRenameName] = useState('');
  const [editEntry, setEditEntry] = useState<SftpEntry | null>(null);
  const [editContent, setEditContent] = useState('');

  const currentHostId = hostId === '' ? null : hostId;

  // 目录永远排在文件前面：给名称加前缀 0/1，复用通用的字符串比较
  const entryAccessors = useMemo(() => ({
    name: (entry: SftpEntry) => `${entry.type === 'directory' ? '0' : '1'}${entry.name.toLowerCase()}`,
    size: (entry: SftpEntry) => (entry.type === 'directory' ? null : entry.size),
    mtime: (entry: SftpEntry) => entry.mtime,
  }), []);

  const fileTable = useTableControls<SftpEntry>({
    data: entries,
    accessors: entryAccessors,
    defaultSortKey: 'name',
    initialPageSize: 20,
  });

  useEffect(() => {
    void api.get<HostOption[]>('/api/hosts')
      .then(res => {
        setHosts(res.data);
        if (res.data.length > 0) {
          setHostId(prev => (prev === '' ? res.data[0].id : prev));
        }
      })
      .catch(error => toast.error('获取主机列表失败', { description: getApiErrorMessage(error) }));
  }, []);

  const loadDir = useCallback(async (hid: number, dir: string) => {
    setLoading(true);
    try {
      const res = await api.get<SftpEntry[]>(`/api/sftp/${hid}/list`, { params: { path: dir } });
      const sorted = [...res.data].sort((a, b) => {
        if (a.type !== b.type) return a.type === 'directory' ? -1 : 1;
        return a.name.localeCompare(b.name);
      });
      setEntries(sorted);
      setPath(dir);
      setPathInput(dir);
    } catch (error) {
      toast.error('读取目录失败', { description: getApiErrorMessage(error) });
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (currentHostId !== null) void loadDir(currentHostId, '/');
  }, [currentHostId, loadDir]);

  const crumbs = useMemo(() => {
    const items = [{ label: '/', path: '/' }];
    let cur = '';
    path.split('/').filter(Boolean).forEach(part => {
      cur += `/${part}`;
      items.push({ label: part, path: cur });
    });
    return items;
  }, [path]);

  const refresh = () => {
    if (currentHostId !== null) void loadDir(currentHostId, path);
  };

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0 || currentHostId === null) return;
    const formData = new FormData();
    formData.append('path', path);
    Array.from(files).forEach(f => formData.append('files[]', f));
    setIsUploading(true);
    try {
      await api.post(`/api/sftp/${currentHostId}/upload`, formData);
      toast.success('上传成功', { description: `已上传 ${files.length} 个文件` });
      await loadDir(currentHostId, path);
    } catch (error) {
      toast.error('上传失败', { description: getApiErrorMessage(error) });
    } finally {
      setIsUploading(false);
      event.target.value = '';
    }
  };

  const handleMkdir = async () => {
    if (currentHostId === null || !mkdirName.trim()) return;
    setIsSaving(true);
    try {
      await api.post(`/api/sftp/${currentHostId}/mkdir`, { path: joinPath(path, mkdirName.trim()) });
      toast.success('已创建目录');
      setMkdirOpen(false);
      setMkdirName('');
      await loadDir(currentHostId, path);
    } catch (error) {
      toast.error('创建目录失败', { description: getApiErrorMessage(error) });
    } finally {
      setIsSaving(false);
    }
  };

  const handleTouch = async () => {
    if (currentHostId === null || !touchName.trim()) return;
    setIsSaving(true);
    try {
      await api.post(`/api/sftp/${currentHostId}/touch`, { path: joinPath(path, touchName.trim()) });
      toast.success('已创建文件');
      setTouchOpen(false);
      setTouchName('');
      await loadDir(currentHostId, path);
    } catch (error) {
      toast.error('创建文件失败', { description: getApiErrorMessage(error) });
    } finally {
      setIsSaving(false);
    }
  };

  const handleRename = async () => {
    if (currentHostId === null || !renameEntry || !renameName.trim()) return;
    setIsSaving(true);
    try {
      await api.post(`/api/sftp/${currentHostId}/rename`, {
        old_path: joinPath(path, renameEntry.name),
        new_path: joinPath(path, renameName.trim()),
      });
      toast.success('重命名成功');
      setRenameEntry(null);
      await loadDir(currentHostId, path);
    } catch (error) {
      toast.error('重命名失败', { description: getApiErrorMessage(error) });
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (entry: SftpEntry) => {
    if (currentHostId === null) return;
    if (!await confirm({
      title: '删除',
      description: `确定删除${entry.type === 'directory' ? '目录' : '文件'}「${entry.name}」吗？此操作不可撤销。`,
      destructive: true,
    })) return;
    try {
      await api.post(`/api/sftp/${currentHostId}/delete`, {
        path: joinPath(path, entry.name),
        is_directory: entry.type === 'directory',
      });
      toast.success('已删除');
      await loadDir(currentHostId, path);
    } catch (error) {
      toast.error('删除失败', { description: getApiErrorMessage(error) });
    }
  };

  const handleDownload = async (entry: SftpEntry) => {
    if (currentHostId === null) return;
    try {
      const res = await api.get(`/api/sftp/${currentHostId}/download`, {
        params: { path: joinPath(path, entry.name) },
        responseType: 'blob',
      });
      const url = URL.createObjectURL(res.data as Blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = entry.name;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (error) {
      toast.error('下载失败', { description: getApiErrorMessage(error) });
    }
  };

  const handleOpenEdit = async (entry: SftpEntry) => {
    if (currentHostId === null) return;
    try {
      const res = await api.get<{ content: string }>(`/api/sftp/${currentHostId}/read`, {
        params: { path: joinPath(path, entry.name) },
      });
      setEditContent(res.data.content);
      setEditEntry(entry);
    } catch (error) {
      toast.error('读取文件失败', { description: getApiErrorMessage(error) });
    }
  };

  const handleSaveEdit = async () => {
    if (currentHostId === null || !editEntry) return;
    setIsSaving(true);
    try {
      await api.post(`/api/sftp/${currentHostId}/write`, {
        path: joinPath(path, editEntry.name),
        content: editContent,
      });
      toast.success('已保存');
      setEditEntry(null);
      await loadDir(currentHostId, path);
    } catch (error) {
      toast.error('保存失败', { description: getApiErrorMessage(error) });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="container mx-auto space-y-6 p-4 md:p-6 lg:p-8">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <span className="h-5 w-[3px] rounded-sm bg-primary" />
          文件管理
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">通过 SFTP 浏览、上传、编辑和下载远程主机上的文件。</p>
      </div>

      <Card className="rounded-md">
        <CardHeader className="border-b pb-4">
          <CardTitle className="flex items-center gap-2 text-base">
            <span className="h-3.5 w-[3px] rounded-sm bg-primary" />
            目标主机
          </CardTitle>
          <CardDescription>选择一台主机后浏览其文件系统。</CardDescription>
        </CardHeader>
        <CardContent className="pt-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <select
              value={hostId}
              onChange={(e) => setHostId(e.target.value ? Number(e.target.value) : '')}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm sm:w-[300px]"
              aria-label="选择主机"
            >
              {hosts.length === 0 && <option value="">暂无主机</option>}
              {hosts.map(h => <option key={h.id} value={h.id}>{h.comment} ({h.address})</option>)}
            </select>
            <Input
              value={pathInput}
              onChange={(e) => setPathInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && currentHostId !== null && pathInput.trim()) {
                  void loadDir(currentHostId, pathInput.trim());
                }
              }}
              placeholder="输入路径后回车跳转，如 /etc"
              className="font-mono text-sm sm:flex-1"
            />
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => currentHostId !== null && void loadDir(currentHostId, parentPath(path))} disabled={path === '/' || currentHostId === null}>
                <ArrowUp className="mr-1 h-4 w-4" /> 上级
              </Button>
              <Button variant="outline" size="sm" onClick={refresh} disabled={currentHostId === null}>
                <RefreshCw className="mr-1 h-4 w-4" /> 刷新
              </Button>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-1 text-sm">
            {crumbs.map((c, i) => (
              <span key={c.path} className="flex items-center gap-1">
                {i > 0 && <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
                <button
                  type="button"
                  onClick={() => currentHostId !== null && void loadDir(currentHostId, c.path)}
                  className={`rounded px-1.5 py-0.5 hover:bg-muted ${i === crumbs.length - 1 ? 'font-medium' : 'text-muted-foreground'}`}
                >
                  {c.label}
                </button>
              </span>
            ))}
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => void handleUpload(e)}
            />
            {isAdmin && (
              <>
                <Button
                  variant="default"
                  size="sm"
                  disabled={isUploading || currentHostId === null}
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload className="mr-1 h-4 w-4" /> {isUploading ? '上传中...' : '上传文件'}
                </Button>
                <Button variant="outline" size="sm" onClick={() => setMkdirOpen(true)} disabled={currentHostId === null}>
                  <FolderPlus className="mr-1 h-4 w-4" /> 新建目录
                </Button>
                <Button variant="outline" size="sm" onClick={() => setTouchOpen(true)} disabled={currentHostId === null}>
                  <FilePlus className="mr-1 h-4 w-4" /> 新建文件
                </Button>
              </>
            )}
            {!isAdmin && (
              <span className="text-xs text-muted-foreground">只读账号：可浏览与下载，不能修改远端文件</span>
            )}
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-md">
        <CardHeader className="border-b pb-4">
          <CardTitle className="flex items-center gap-2 text-base">
            <span className="h-3.5 w-[3px] rounded-sm bg-primary" />
            {path}
          </CardTitle>
          <CardDescription>共 {entries.length} 项。</CardDescription>
        </CardHeader>
        <CardContent className="pt-4">
          <div className="border rounded-md overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/60 hover:bg-muted/60">
                  <SortableHead sortKey="name" activeKey={fileTable.sortKey} dir={fileTable.sortDir} onSort={fileTable.toggleSort}>名称</SortableHead>
                  <SortableHead sortKey="size" className="hidden sm:table-cell" activeKey={fileTable.sortKey} dir={fileTable.sortDir} onSort={fileTable.toggleSort}>大小</SortableHead>
                  <SortableHead sortKey="mtime" className="hidden md:table-cell" activeKey={fileTable.sortKey} dir={fileTable.sortDir} onSort={fileTable.toggleSort}>修改时间</SortableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow><TableCell colSpan={4} className="text-center py-8">加载中...</TableCell></TableRow>
                ) : hosts.length === 0 ? (
                  <TableRow><TableCell colSpan={4} className="text-center py-8 text-muted-foreground">请先在「主机管理」中添加主机</TableCell></TableRow>
                ) : entries.length > 0 ? fileTable.pageRows.map(entry => (
                  <TableRow key={`${entry.type}-${entry.name}`}>
                    <TableCell>
                      <button
                        type="button"
                        onClick={() => {
                          if (entry.type === 'directory' && currentHostId !== null) {
                            void loadDir(currentHostId, joinPath(path, entry.name));
                          } else {
                            void handleOpenEdit(entry);
                          }
                        }}
                        className="flex items-center gap-2 text-sm hover:underline"
                      >
                        {entry.type === 'directory'
                          ? <Folder className="h-4 w-4 shrink-0 text-primary" />
                          : <FileIcon className="h-4 w-4 shrink-0 text-muted-foreground" />}
                        <span>{entry.name}</span>
                      </button>
                    </TableCell>
                    <TableCell className="hidden sm:table-cell text-xs text-muted-foreground">
                      {entry.type === 'directory' ? '-' : formatSize(entry.size)}
                    </TableCell>
                    <TableCell className="hidden md:table-cell text-xs text-muted-foreground">
                      {new Date(entry.mtime * 1000).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right space-x-0.5">
                      {entry.type === 'file' && (
                        <>
                          <Button variant="ghost" size="icon" title="下载" onClick={() => void handleDownload(entry)}>
                            <Download className="h-4 w-4" />
                          </Button>
                          {isAdmin && (
                            <Button variant="ghost" size="icon" title="编辑" onClick={() => void handleOpenEdit(entry)}>
                              <Pencil className="h-4 w-4" />
                            </Button>
                          )}
                        </>
                      )}
                      {isAdmin && (
                        <>
                          <Button variant="ghost" size="icon" title="重命名" onClick={() => { setRenameEntry(entry); setRenameName(entry.name); }}>
                            <span className="text-xs">Aa</span>
                          </Button>
                          <Button variant="ghost" size="icon" title="删除" onClick={() => void handleDelete(entry)} className="text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300">
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </>
                      )}
                    </TableCell>
                  </TableRow>
                )) : (
                  <TableRow><TableCell colSpan={4} className="text-center py-8 text-muted-foreground">空目录</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
            <TablePagination
              page={fileTable.page}
              pageCount={fileTable.pageCount}
              pageSize={fileTable.pageSize}
              total={fileTable.total}
              onPageChange={fileTable.setPage}
              onPageSizeChange={fileTable.setPageSize}
            />
          </div>
        </CardContent>
      </Card>

      <Dialog open={mkdirOpen} onOpenChange={setMkdirOpen}>
        <DialogContent className="sm:max-w-[420px]">
          <DialogHeader>
            <DialogTitle>新建目录</DialogTitle>
            <DialogDescription>将在 {path} 下创建。</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="mkdir-name">目录名称</Label>
            <Input id="mkdir-name" value={mkdirName} onChange={(e) => setMkdirName(e.target.value)} placeholder="例如 logs" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setMkdirOpen(false)}>取消</Button>
            <Button onClick={() => void handleMkdir()} disabled={isSaving || !mkdirName.trim()}>{isSaving ? '创建中...' : '创建'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={touchOpen} onOpenChange={setTouchOpen}>
        <DialogContent className="sm:max-w-[420px]">
          <DialogHeader>
            <DialogTitle>新建文件</DialogTitle>
            <DialogDescription>将在 {path} 下创建空文件。</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="touch-name">文件名称</Label>
            <Input id="touch-name" value={touchName} onChange={(e) => setTouchName(e.target.value)} placeholder="例如 app.conf" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTouchOpen(false)}>取消</Button>
            <Button onClick={() => void handleTouch()} disabled={isSaving || !touchName.trim()}>{isSaving ? '创建中...' : '创建'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!renameEntry} onOpenChange={(open) => !open && setRenameEntry(null)}>
        <DialogContent className="sm:max-w-[420px]">
          <DialogHeader>
            <DialogTitle>重命名</DialogTitle>
            <DialogDescription>当前名称：{renameEntry?.name}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="rename-name">新名称</Label>
            <Input id="rename-name" value={renameName} onChange={(e) => setRenameName(e.target.value)} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenameEntry(null)}>取消</Button>
            <Button onClick={() => void handleRename()} disabled={isSaving || !renameName.trim()}>{isSaving ? '保存中...' : '保存'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!editEntry} onOpenChange={(open) => !open && setEditEntry(null)}>
        <DialogContent className="sm:max-w-[760px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>编辑文件：{editEntry?.name}</DialogTitle>
            <DialogDescription>{path}</DialogDescription>
          </DialogHeader>
          <Textarea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            className="font-mono text-sm min-h-[380px]"
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditEntry(null)}>取消</Button>
            <Button onClick={() => void handleSaveEdit()} disabled={isSaving}>{isSaving ? '保存中...' : '保存'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default FilesPage;
