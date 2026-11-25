import { useEffect, useState } from 'react';
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import api from '@/services/api';
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import { CheckCircleIcon, XCircleIcon } from 'lucide-react';
import { getApiErrorMessage } from '@/utils/http';
import { Checkbox } from "@/components/ui/checkbox";

interface PlaybookExecutorProps {
  targetHostIds?: number[] | 'all';
  initialPlaybookId?: number;
  onClose: () => void;
}

interface SavedPlaybook {
  id: number;
  name: string;
  description: string;
  content: string;
}

interface HostOption {
  id: number;
  comment: string;
  address: string;
}

interface PlaybookResult {
  success: boolean;
  return_code: number;
  logs: string[];
  summary: {
    success: string[];
    failed: string[];
    unreachable: string[];
  };
}

const defaultPlaybook = `---
# Ansible Playbook 示例
- name: 示例任务
  hosts: all
  tasks:
    - name: 执行一个简单的命令
      command: echo "Hello, Ansible!"
      register: hello_result

    - name: 显示命令结果
      debug:
        var: hello_result.stdout
`;

function PlaybookExecutor({ targetHostIds, initialPlaybookId, onClose }: PlaybookExecutorProps) {
  const [playbook, setPlaybook] = useState(defaultPlaybook);
  const [savedPlaybooks, setSavedPlaybooks] = useState<SavedPlaybook[]>([]);
  const [selectedPlaybookId, setSelectedPlaybookId] = useState<number | ''>(initialPlaybookId ?? '');
  const [hosts, setHosts] = useState<HostOption[]>([]);
  const [selectedHostIds, setSelectedHostIds] = useState<number[]>([]);
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionProgress, setExecutionProgress] = useState(0);
  const [executionResult, setExecutionResult] = useState<PlaybookResult | null>(null);
  const [extraVarsText, setExtraVarsText] = useState('');

  useEffect(() => {
    void api.get<SavedPlaybook[]>('/api/playbooks').then(res => {
      setSavedPlaybooks(res.data);
      if (initialPlaybookId) {
        const pb = res.data.find(item => item.id === initialPlaybookId);
        if (pb) setPlaybook(pb.content);
      }
    }).catch(() => {
      // 列表加载失败不影响手动输入 playbook
    });
    if (!targetHostIds) {
      void api.get<HostOption[]>('/api/hosts').then(res => {
        setHosts(res.data);
      }).catch(() => {
        // 主机列表加载失败时仍可尝试对全部主机执行
      });
    }
  }, [targetHostIds, initialPlaybookId]);

  // 解析「每行 key=value」的变量输入，值尽量按 JSON 解析，否则当字符串
  const parseExtraVars = (text: string): Record<string, unknown> => {
    const parsed: Record<string, unknown> = {};
    text.split('\n').forEach(line => {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) return;
      const idx = trimmed.indexOf('=');
      if (idx <= 0) return;
      const key = trimmed.slice(0, idx).trim();
      const raw = trimmed.slice(idx + 1).trim();
      if (!key) return;
      try {
        parsed[key] = JSON.parse(raw);
      } catch {
        parsed[key] = raw;
      }
    });
    return parsed;
  };

  const handleSelectPlaybook = (value: string) => {
    if (!value) {
      setSelectedPlaybookId('');
      return;
    }
    const id = Number(value);
    setSelectedPlaybookId(id);
    const pb = savedPlaybooks.find(item => item.id === id);
    if (pb) setPlaybook(pb.content);
  };

  const handleExecution = async () => {
    if (!playbook.trim() && !selectedPlaybookId) {
      toast.error("错误", { description: "请输入或选择 Playbook" });
      return;
    }

    let finalHostIds: number[] | 'all';
    if (targetHostIds) {
      finalHostIds = targetHostIds;
    } else if (selectedHostIds.length > 0) {
      finalHostIds = selectedHostIds;
    } else {
      finalHostIds = 'all';
    }

    setIsExecuting(true);
    setExecutionProgress(10);
    setExecutionResult(null);

    try {
      const requestData: Record<string, unknown> = {
        host_ids: finalHostIds === 'all' ? [] : finalHostIds,
      };
      if (selectedPlaybookId) {
        requestData.playbook_id = selectedPlaybookId;
      } else {
        requestData.playbook = playbook.trim();
      }
      const extraVars = parseExtraVars(extraVarsText);
      if (Object.keys(extraVars).length > 0) {
        requestData.extra_vars = extraVars;
      }

      setExecutionProgress(30);
      const response = await api.post<PlaybookResult>("/api/playbook/execute", requestData);
      setExecutionProgress(100);

      setExecutionResult(response.data);
      if (response.data.success) {
        const failedCount = response.data.summary.failed.length;
        const unreachableCount = response.data.summary.unreachable.length;
        if (failedCount === 0 && unreachableCount === 0) {
          toast.success("Playbook执行成功", { description: "所有主机任务完成" });
        } else {
          toast.warning("Playbook部分执行成功", {
            description: `成功: ${response.data.summary.success.length}台, 失败: ${failedCount}台, 不可达: ${unreachableCount}台`
          });
        }
      } else {
        toast.error("Playbook执行失败", {
          description: `执行失败，返回代码: ${response.data.return_code}`,
        });
      }
    } catch (error) {
      console.error('Playbook execution failed:', error);
      toast.error("Playbook执行失败", { description: getApiErrorMessage(error) });
    } finally {
      setIsExecuting(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-2">
        <Label htmlFor="savedPlaybookSelect">选择已保存的 Playbook（可选）</Label>
        <select
          id="savedPlaybookSelect"
          value={selectedPlaybookId}
          onChange={(e) => handleSelectPlaybook(e.target.value)}
          disabled={isExecuting}
          className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
        >
          <option value="">-- 手动输入 Playbook --</option>
          {savedPlaybooks.map(pb => (
            <option key={pb.id} value={pb.id}>{pb.name}</option>
          ))}
        </select>
      </div>

      {!targetHostIds && (
        <div className="grid gap-2">
          <Label>目标主机（不选择则对全部主机执行）</Label>
          <div className="max-h-[120px] overflow-y-auto rounded-md border p-2 space-y-2">
            {hosts.length > 0 ? hosts.map(host => (
              <label key={host.id} className="flex items-center gap-2 text-sm cursor-pointer">
                <Checkbox
                  checked={selectedHostIds.includes(host.id)}
                  onCheckedChange={(checked) => setSelectedHostIds(prev =>
                    checked ? [...prev, host.id] : prev.filter(id => id !== host.id)
                  )}
                />
                <span>{host.comment} ({host.address})</span>
              </label>
            )) : <span className="text-xs text-muted-foreground">暂无主机，将对全部主机执行</span>}
          </div>
        </div>
      )}

      <div className="grid gap-2">
        <Label htmlFor="playbookContent">Playbook 内容 (YAML)</Label>
        <Textarea
          id="playbookContent"
          placeholder="输入Ansible Playbook内容..."
          value={playbook}
          onChange={(e) => {
            setPlaybook(e.target.value);
            setSelectedPlaybookId('');
          }}
          className="font-mono text-sm min-h-[260px]"
          disabled={isExecuting}
        />
        <p className="text-xs text-muted-foreground">选择已保存的 Playbook 后内容会载入此处，修改内容后将作为自定义 Playbook 执行。</p>
      </div>

      <div className="grid gap-2">
        <Label htmlFor="extraVars">执行变量（可选，每行 key=value）</Label>
        <Textarea
          id="extraVars"
          placeholder={"target_dir=/tmp\nretries=3\nenabled=true"}
          value={extraVarsText}
          onChange={(e) => setExtraVarsText(e.target.value)}
          className="font-mono text-sm min-h-[80px]"
          disabled={isExecuting}
        />
        <p className="text-xs text-muted-foreground">值支持 JSON 数字/布尔/数组，其余按字符串处理；等价于 ansible-playbook -e。</p>
      </div>

      {isExecuting && <Progress value={executionProgress} className="w-full" />}

      {executionResult && (
        <div className="border rounded-md p-3 bg-muted/90">
          <h4 className="text-sm font-medium mb-2">执行结果</h4>
          <p className="text-sm mb-2">
            {executionResult.success ? "Playbook执行成功" : "Playbook执行失败"}
            (返回代码: {executionResult.return_code})
          </p>

          <div className="text-xs space-y-1 mb-3">
            {executionResult.summary.success.length > 0 && (
              <div>
                <p className="font-medium text-green-600 dark:text-green-400 flex items-center gap-1">
                  <CheckCircleIcon className="h-3 w-3" />
                  成功主机 ({executionResult.summary.success.length})
                </p>
                <ul className="pl-5 list-disc">
                  {executionResult.summary.success.map(host => <li key={`success-${host}`}>{host}</li>)}
                </ul>
              </div>
            )}
            {executionResult.summary.failed.length > 0 && (
              <div>
                <p className="font-medium text-red-600 dark:text-red-400 flex items-center gap-1 mt-2">
                  <XCircleIcon className="h-3 w-3" />
                  失败主机 ({executionResult.summary.failed.length})
                </p>
                <ul className="pl-5 list-disc">
                  {executionResult.summary.failed.map(host => <li key={`fail-${host}`}>{host}</li>)}
                </ul>
              </div>
            )}
            {executionResult.summary.unreachable.length > 0 && (
              <div>
                <p className="font-medium text-yellow-600 dark:text-yellow-400 flex items-center gap-1 mt-2">
                  <XCircleIcon className="h-3 w-3" />
                  不可达主机 ({executionResult.summary.unreachable.length})
                </p>
                <ul className="pl-5 list-disc">
                  {executionResult.summary.unreachable.map(host => <li key={`unreachable-${host}`}>{host}</li>)}
                </ul>
              </div>
            )}
          </div>

          <div className="mt-4">
            <h5 className="text-sm font-medium mb-1">详细日志</h5>
            <div className="bg-black text-green-400 p-2 rounded font-mono text-xs h-[200px] overflow-y-auto whitespace-pre-wrap">
              {executionResult.logs.join('\n')}
            </div>
          </div>
        </div>
      )}

      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose} disabled={isExecuting}>
          {executionResult ? '关闭' : '取消'}
        </Button>
        {!executionResult && (
          <Button onClick={handleExecution} disabled={(!playbook.trim() && !selectedPlaybookId) || isExecuting}>
            {isExecuting ? '执行中...' : '执行 Playbook'}
          </Button>
        )}
        {executionResult && <Button variant="default" onClick={onClose}>完成</Button>}
      </div>
    </div>
  );
}

export default PlaybookExecutor;
