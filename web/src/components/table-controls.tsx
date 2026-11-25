import type { ReactNode } from 'react';
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsUpDown } from 'lucide-react';
import { TableHead } from '@/components/ui/table';
import { cn } from '@/lib/utils';
import type { SortDir } from '@/hooks/useTableControls';

interface SortableHeadProps {
  /** 本列在 accessors 中的 key */
  sortKey: string;
  activeKey: string | null;
  dir: SortDir;
  onSort: (key: string) => void;
  children: ReactNode;
  className?: string;
  align?: 'left' | 'right' | 'center';
}

/** 可点击排序的表头。未激活时显示双向箭头，激活后显示当前方向 */
function SortableHead({ sortKey, activeKey, dir, onSort, children, className, align = 'left' }: SortableHeadProps) {
  const active = activeKey === sortKey;
  const Icon = !active ? ChevronsUpDown : dir === 'asc' ? ArrowUp : ArrowDown;

  return (
    <TableHead
      className={className}
      aria-sort={active ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={cn(
          'inline-flex items-center gap-1 rounded transition-colors hover:text-foreground',
          active ? 'font-semibold text-foreground' : 'text-inherit',
          align === 'right' && 'flex-row-reverse',
          align === 'center' && 'justify-center'
        )}
      >
        {children}
        <Icon className={cn('h-3 w-3 shrink-0', active ? 'opacity-90' : 'opacity-40')} />
      </button>
    </TableHead>
  );
}

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

interface TablePaginationProps {
  page: number;
  pageCount: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
}

/** 生成页码序列，超过 7 页时用省略号折叠 */
function buildPageList(current: number, count: number): (number | 'gap')[] {
  if (count <= 7) return Array.from({ length: count }, (_, i) => i + 1);
  const pages = new Set<number>([1, count, current]);
  if (current - 1 > 1) pages.add(current - 1);
  if (current + 1 < count) pages.add(current + 1);

  const sorted = [...pages].sort((a, b) => a - b);
  const result: (number | 'gap')[] = [];
  sorted.forEach((page, index) => {
    if (index > 0 && page - sorted[index - 1] > 1) result.push('gap');
    result.push(page);
  });
  return result;
}

function TablePagination({ page, pageCount, pageSize, total, onPageChange, onPageSizeChange }: TablePaginationProps) {
  if (total === 0) return null;

  const pages = buildPageList(page, pageCount);
  const navButtonClass =
    'flex h-7 w-7 items-center justify-center rounded border border-input text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent';

  return (
    <div className="flex flex-col-reverse items-center justify-between gap-3 border-t border-border pt-3 text-xs sm:flex-row">
      <div className="flex items-center gap-3 text-muted-foreground">
        <span>共 {total} 条</span>
        <span className="hidden sm:inline">·</span>
        <label className="hidden items-center gap-1.5 sm:flex">
          每页
          <select
            value={pageSize}
            onChange={e => onPageSizeChange(Number(e.target.value))}
            aria-label="每页条数"
            className="h-7 rounded border border-input bg-background px-1.5 text-xs"
          >
            {PAGE_SIZE_OPTIONS.map(size => (
              <option key={size} value={size}>{size}</option>
            ))}
          </select>
          条
        </label>
      </div>

      <div className="flex items-center gap-1">
        <button
          type="button"
          className={navButtonClass}
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          aria-label="上一页"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>

        {pages.map((item, index) =>
          item === 'gap' ? (
            <span key={`gap-${index}`} className="px-1 text-muted-foreground">…</span>
          ) : (
            <button
              key={item}
              type="button"
              onClick={() => onPageChange(item)}
              aria-current={item === page ? 'page' : undefined}
              className={cn(
                'h-7 min-w-7 rounded border px-1.5 transition-colors',
                item === page
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-input text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              )}
            >
              {item}
            </button>
          )
        )}

        <button
          type="button"
          className={navButtonClass}
          onClick={() => onPageChange(page + 1)}
          disabled={page >= pageCount}
          aria-label="下一页"
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

export { SortableHead, TablePagination };
