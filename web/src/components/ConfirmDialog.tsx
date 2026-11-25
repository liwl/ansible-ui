import { useCallback, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

interface ConfirmOptions {
  title: string;
  description?: string;
  confirmText?: string;
  cancelText?: string;
  destructive?: boolean;
}

type ConfirmRequest = ConfirmOptions & {
  resolve: (value: boolean) => void;
};

// 全局单例状态，让 confirm() 可以在任意组件中调用
let confirmHandler: ((options: ConfirmOptions) => Promise<boolean>) | null = null;

export const confirm = (options: ConfirmOptions): Promise<boolean> => {
  if (!confirmHandler) {
    // 兜底：组件未挂载时用原生 confirm
    return Promise.resolve(typeof window !== 'undefined' && window.confirm(options.description || options.title));
  }
  return confirmHandler(options);
};

export function ConfirmDialogProvider({ children }: { children: React.ReactNode }) {
  const [request, setRequest] = useState<ConfirmRequest | null>(null);

  const handler = useCallback((options: ConfirmOptions): Promise<boolean> => {
    return new Promise<boolean>((resolve) => {
      setRequest({ ...options, resolve });
    });
  }, []);

  // 注册全局 handler
  confirmHandler = handler;

  const settle = (value: boolean) => {
    request?.resolve(value);
    setRequest(null);
  };

  return (
    <>
      {children}
      <Dialog open={!!request} onOpenChange={(open) => { if (!open) settle(false); }}>
        <DialogContent className="sm:max-w-[420px]">
          <DialogHeader>
            <DialogTitle>{request?.title ?? ''}</DialogTitle>
            {request?.description && (
              <DialogDescription>{request.description}</DialogDescription>
            )}
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => settle(false)}>
              {request?.cancelText ?? '取消'}
            </Button>
            <Button
              variant={request?.destructive ? 'destructive' : 'default'}
              onClick={() => settle(true)}
            >
              {request?.confirmText ?? '确定'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
