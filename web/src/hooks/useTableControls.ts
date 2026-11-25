import { useCallback, useEffect, useMemo, useState } from 'react';

export type SortDir = 'asc' | 'desc';

/** 取列值的函数；返回值用于排序，返回 undefined / null 的排在最后 */
export type Accessor<T> = (row: T) => string | number | null | undefined;

export interface UseTableControlsOptions<T> {
  /** 已过滤好的原始数据 */
  data: T[];
  /** 列 key → 取值函数。只有出现在这里的 key 才可排序 */
  accessors?: Record<string, Accessor<T>>;
  defaultSortKey?: string;
  defaultSortDir?: SortDir;
  initialPageSize?: number;
}

export interface TableControls<T> {
  /** 当前页的数据 */
  pageRows: T[];
  page: number;
  setPage: (page: number) => void;
  pageSize: number;
  setPageSize: (size: number) => void;
  pageCount: number;
  total: number;
  sortKey: string | null;
  sortDir: SortDir;
  /** 点击表头：同列切换方向，换列则回到升序 */
  toggleSort: (key: string) => void;
}

const EMPTY = '';

function normalize(value: string | number | null | undefined): { empty: boolean; num?: number; text: string } {
  if (value === null || value === undefined || value === EMPTY) {
    return { empty: true, text: EMPTY };
  }
  if (typeof value === 'number') {
    return { empty: Number.isNaN(value), num: value, text: String(value) };
  }
  return { empty: value.trim() === '', num: undefined, text: value };
}

/**
 * 表格排序 + 分页的统一逻辑。
 * - 中文按 pinyin 无关的 localeCompare（zh-CN），数字串按数值比较，空值恒排最后
 * - 数据变化导致页码越界时自动回退到最后一页
 */
export function useTableControls<T>({
  data,
  accessors,
  defaultSortKey,
  defaultSortDir = 'asc',
  initialPageSize = 10,
}: UseTableControlsOptions<T>): TableControls<T> {
  const [page, setPageState] = useState(1);
  const [pageSize, setPageSizeState] = useState(initialPageSize);
  const [sortKey, setSortKey] = useState<string | null>(defaultSortKey ?? null);
  const [sortDir, setSortDir] = useState<SortDir>(defaultSortDir);

  const sorted = useMemo(() => {
    if (!sortKey || !accessors?.[sortKey]) return data;
    const getValue = accessors[sortKey];
    const factor = sortDir === 'asc' ? 1 : -1;

    return [...data].sort((a, b) => {
      const left = normalize(getValue(a));
      const right = normalize(getValue(b));
      // 空值恒排最后，不随升降序翻转
      if (left.empty && right.empty) return 0;
      if (left.empty) return 1;
      if (right.empty) return -1;

      if (left.num !== undefined && right.num !== undefined) {
        return (left.num - right.num) * factor;
      }
      return left.text.localeCompare(right.text, 'zh-CN', { numeric: true, sensitivity: 'base' }) * factor;
    });
  }, [data, accessors, sortKey, sortDir]);

  const total = sorted.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(page, pageCount);

  // 数据变少（筛选、删除）后把越界的页码写回去，避免下次数据变多时莫名跳页
  useEffect(() => {
    if (page > pageCount) setPageState(pageCount);
  }, [page, pageCount]);

  const pageRows = useMemo(() => {
    const start = (safePage - 1) * pageSize;
    return sorted.slice(start, start + pageSize);
  }, [sorted, safePage, pageSize]);

  const setPage = useCallback((next: number) => {
    setPageState(next);
  }, []);

  const setPageSize = useCallback((size: number) => {
    setPageSizeState(size);
    setPageState(1);
  }, []);

  const toggleSort = useCallback((key: string) => {
    // 注意：不要在 setState 的 updater 里调用另一个 setState，
    // StrictMode 下 updater 会被重复执行，方向会被切换两次而失效
    if (key === sortKey) {
      setSortDir(dir => (dir === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
    setPageState(1);
  }, [sortKey]);

  return {
    pageRows,
    page: safePage,
    setPage,
    pageSize,
    setPageSize,
    pageCount,
    total,
    sortKey,
    sortDir,
    toggleSort,
  };
}
