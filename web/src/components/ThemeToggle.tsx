import { useTheme } from 'next-themes';
import { useEffect, useState } from 'react';
import { Monitor, Moon, Sun } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

const OPTIONS = [
  { value: 'light', label: '浅色', icon: Sun },
  { value: 'dark', label: '深色', icon: Moon },
  { value: 'system', label: '跟随系统', icon: Monitor },
] as const;

/**
 * 主题切换按钮：浅色 / 深色 / 跟随系统。
 * 选择写入 localStorage，由 next-themes 在首屏脚本中提前应用，避免闪烁。
 */
function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  // next-themes 在挂载前无法得知真实主题，用 mounted 规避服务端/首屏不一致
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const Icon = !mounted ? Sun : resolvedTheme === 'dark' ? Moon : Sun;
  const currentLabel = OPTIONS.find(o => o.value === theme)?.label ?? '跟随系统';

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          title={`主题：${currentLabel}`}
          aria-label={`切换主题，当前：${currentLabel}`}
          className="flex h-7 w-7 items-center justify-center rounded border border-white/40 bg-white/15 text-white transition-colors hover:bg-white/25"
        >
          <Icon size={14} />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-32">
        {OPTIONS.map(option => {
          const OptionIcon = option.icon;
          return (
            <DropdownMenuItem
              key={option.value}
              onSelect={() => setTheme(option.value)}
              className="gap-2 text-xs"
            >
              <OptionIcon size={13} />
              {option.label}
              {theme === option.value && <span className="ml-auto text-primary">✓</span>}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export default ThemeToggle;
