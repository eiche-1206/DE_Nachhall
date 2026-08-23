/* 右下角提示。
 *
 * 成功停 3s 自动走，错误停 6s 且**带关闭按钮** —— 错误信息里有用户需要
 * 照着做的东西（换个链接、去设置里开麦克风），不能在他读完之前消失。
 *
 * 设置切换不发 Toast：即时生效本身就是反馈，再弹一次是噪音。
 */

import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';

import './Toast.css';

export type ToastKind = 'ok' | 'err';

interface ToastItem {
  id: number;
  kind: ToastKind;
  text: string;
}

const HOLD_MS: Record<ToastKind, number> = { ok: 3000, err: 6000 };

interface Ctx {
  toast: (text: string, kind?: ToastKind) => void;
}

const ToastContext = createContext<Ctx | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const seq = useRef(0);

  const dismiss = useCallback((id: number) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (text: string, kind: ToastKind = 'ok') => {
      const id = ++seq.current;
      setItems((prev) => [...prev, { id, kind, text }]);
      window.setTimeout(() => dismiss(id), HOLD_MS[kind]);
    },
    [dismiss]
  );

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast toast--${t.kind}`}>
            <span className="toast__text">{t.text}</span>
            {t.kind === 'err' ? (
              <button className="toast__close" onClick={() => dismiss(t.id)} aria-label="关闭">
                ×
              </button>
            ) : null}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): Ctx {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast 必须在 <ToastProvider> 内使用');
  return ctx;
}
