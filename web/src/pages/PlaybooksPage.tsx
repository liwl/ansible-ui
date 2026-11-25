import { useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import api from '@/services/api';
import { Pencil1Icon, TrashIcon, PlayIcon, PlusCircledIcon } from '@radix-ui/react-icons';
import { Search, Download, Upload } from 'lucide-react';
import { getApiErrorMessage } from '@/utils/http';
import { confirm } from '@/components/ConfirmDialog';
import PlaybookExecutor from '@/components/PlaybookExecutor';
import { useAuth } from '@/contexts/use-auth';

interface Playbook {
  id: number;
  name: string;
  description: string;
  content: string;
  created_at: string;
  updated_at: string;
}

interface FormState {
  name: string;
  description: string;
  content: string;
}

const emptyForm: FormState = { name: '', description: '', content: '' };

function PlaybooksPage() {
  const { isAdmin } = useAuth();
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [search, setSearch] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [executingPlaybook, setExecutingPlaybook] = useState<Playbook | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const fetchPlaybooks = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await api.get<Playbook[]>('/api/playbooks');
      setPlaybooks(response.data);
    } catch (error) {
      toast.error("获取 Playbook 列表失败", { description: getApiErrorMessage(error, "无法连接到服务器") });
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchPlaybooks();
  }, [fetchPlaybooks]);

  const filteredPlaybooks = playbooks.filter(pb => {
    const keyword = search.trim().toLowerCase();
    if (!keyword) return true;
    return [pb.name, pb.description].some(value => (value ?? '').toLowerCase().includes(keyword));
  });

  const openCreate = () => {
    setForm(emptyForm);
    setEditingId(null);
    setIsFormOpen(true);
  };

  const openEdit = (pb: Playbook) => {
    setForm({ name: pb.name, description: pb.description || '', content: pb.content });
    setEditingId(pb.id);
    setIsFormOpen(true);
  };

  const handleSave = async () => {
    if (!form.name.trim()) {
      toast.error("错误", { description: "请输入 Playbook 名称" });
      return;
    }
    if (!form.content.trim()) {
      toast.error("错误", { description: "请输入 Playbook 内容" });
      return;
    }
    setIsSaving(true);
    try {
      if (editingId) {
        await api.put(`/api/playbooks/${editingId}`, form);
        toast.success("成功", { description: "Playbook 已更新" });
      } else {
        await api.post('/api/playbooks', form);
        toast.success("成功", { description: "Playbook 已保存" });
      }
      setIsFormOpen(false);
      await fetchPlaybooks();
    } catch (error) {
      toast.error("保存失败", { description: getApiErrorMessage(error) });
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (pb: Playbook) => {
    if (!await confirm({
      title: '删除 Playbook',
      description: `确定要删除 Playbook「${pb.name}」吗？此操作不可撤销。`,
      destructive: true,
    })) return;
    try {
      await api.delete(`/api/playbooks/${pb.id}`);
      toast.success("成功", { description: `Playbook「${pb.name}」已删除` });
      await fetchPlaybooks();
    } catch (error) {
      toast.error("删除失败", { description: getApiErrorMessage(error) });
    }
  };

  // 导入本地 YAML 文件：读取内容后打开新增弹窗，确认信息再保存
  const handleImportFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const content = await file.text();
      if (!content.trim()) {
        toast.error("导入失败", { description: "文件内容为空" });
        return;
      }
      setForm({
        name: file.name.replace(/\.(yml|yaml)$/i, ''),
        description: `从 ${file.name} 导入`,
        content,
      });
      setEditingId(null);
      setIsFormOpen(true);
      toast.success("已读取 YAML", { description: "确认名称和内容后点击保存" });
    } catch {
      toast.error("导入失败", { description: "无法读取该文件" });
    } finally {
      event.target.value = '';
    }
  };

  // 导出为 <名称>.yml 文件
  const handleExport = (pb: Playbook) => {
    const blob = new Blob([pb.content], { type: 'text/yaml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${pb.name.replace(/[\\/:*?"<>|]/g, '_')}.yml`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    toast.success("已导出", { description: link.download });
  };

  return (
    <div className="container mx-auto p-4 md:p-6 lg:p-8 space-y-6">
      <header className="flex flex-col sm:flex-row justify-between items-center gap-4">
        <div>
          <h1 className="flex items-center gap-2.5 text-2xl font-semibold sm:text-[26px]">
            <span className="h-[18px] w-[3px] rounded-sm bg-primary" />
            Playbook 管理
          </h1>
          <p className="mt-1.5 pl-[13px] text-xs text-muted-foreground">保存常用 Playbook，执行任务时可直接选择。</p>
        </div>
        <Button variant="outline" onClick={() => navigate('/')}>返回主机管理</Button>
      </header>

      <Card className="rounded-md">
        <CardHeader className="border-b pb-4">
          <CardTitle className="flex items-center gap-2 text-base">
            <span className="h-3.5 w-[3px] rounded-sm bg-primary" />
            Playbook 列表
          </CardTitle>
          <CardDescription>共 {playbooks.length} 个 Playbook。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col sm:flex-row justify-between items-center gap-2">
            <div className="relative w-full sm:max-w-xs">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="搜索名称或描述..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <input
                ref={fileInputRef}
                type="file"
                accept=".yml,.yaml,text/yaml,text/plain"
                className="hidden"
                onChange={(e) => void handleImportFile(e)}
              />
              {isAdmin && (
                <>
                  <Button variant="outline" onClick={() => fileInputRef.current?.click()}>
                    <Upload className="mr-2 h-4 w-4" /> 导入 YAML
                  </Button>
                  <Button onClick={openCreate}>
                    <PlusCircledIcon className="mr-2 h-4 w-4" /> 新增 Playbook
                  </Button>
                </>
              )}
            </div>
          </div>

          <div className="border rounded-md overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/60 hover:bg-muted/60">
                  <TableHead>名称</TableHead>
                  <TableHead className="hidden md:table-cell">描述</TableHead>
                  <TableHead className="hidden lg:table-cell">更新时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading ? (
                  <TableRow><TableCell colSpan={4} className="text-center py-4">加载中...</TableCell></TableRow>
                ) : filteredPlaybooks.length > 0 ? (
                  filteredPlaybooks.map((pb) => (
                    <TableRow key={pb.id}>
                      <TableCell className="font-medium">{pb.name}</TableCell>
                      <TableCell className="hidden md:table-cell text-muted-foreground text-sm">
                        {pb.description || '-'}
                      </TableCell>
                      <TableCell className="hidden lg:table-cell text-sm text-muted-foreground">
                        {new Date(pb.updated_at).toLocaleString()}
                      </TableCell>
                      <TableCell className="text-right space-x-1">
                        {isAdmin && (
                          <Button variant="outline" size="sm" onClick={() => setExecutingPlaybook(pb)}>
                            <PlayIcon className="mr-1 h-4 w-4" />执行
                          </Button>
                        )}
                        <Button variant="ghost" size="icon" title="导出 YAML" onClick={() => handleExport(pb)}>
                          <Download className="h-4 w-4" />
                        </Button>
                        {isAdmin && (
                          <>
                            <Button variant="ghost" size="icon" onClick={() => openEdit(pb)}>
                              <Pencil1Icon className="h-4 w-4" />
                            </Button>
                            <Button variant="ghost" size="icon" onClick={() => handleDelete(pb)} className="text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300">
                              <TrashIcon className="h-4 w-4" />
                            </Button>
                          </>
                        )}
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow><TableCell colSpan={4} className="text-center py-4">
                    {search.trim() ? `没有找到匹配 "${search}" 的 Playbook` : '还没有保存的 Playbook，点击「新增 Playbook」创建'}
                  </TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Dialog open={isFormOpen} onOpenChange={setIsFormOpen}>
        <DialogContent className="sm:max-w-[720px]">
          <DialogHeader>
            <DialogTitle>{editingId ? '编辑 Playbook' : '新增 Playbook'}</DialogTitle>
            <DialogDescription>填写名称、描述和 YAML 内容后保存。</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="grid gap-2">
              <Label htmlFor="pb-name">名称</Label>
              <Input id="pb-name" placeholder="例如：批量更新系统" value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="pb-desc">描述</Label>
              <Input id="pb-desc" placeholder="可选，简单说明用途" value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="pb-content">Playbook 内容 (YAML)</Label>
              <Textarea id="pb-content" value={form.content}
                onChange={(e) => setForm({ ...form, content: e.target.value })}
                className="font-mono text-sm min-h-[320px]" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsFormOpen(false)}>取消</Button>
            <Button onClick={handleSave} disabled={isSaving}>{isSaving ? '保存中...' : '保存'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!executingPlaybook} onOpenChange={(open) => !open && setExecutingPlaybook(null)}>
        <DialogContent className="sm:max-w-[760px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>执行 Playbook：{executingPlaybook?.name}</DialogTitle>
            <DialogDescription>选择目标主机后执行。</DialogDescription>
          </DialogHeader>
          {executingPlaybook && (
            <PlaybookExecutor
              initialPlaybookId={executingPlaybook.id}
              onClose={() => setExecutingPlaybook(null)}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default PlaybooksPage;
