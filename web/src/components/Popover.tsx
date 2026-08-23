/* 锚在顶栏右下的浮层外壳。ImportSheet 与 SettingsPanel 共用。
 *
 * Esc 关闭、点外部关闭。做成组件而不是各写一遍，是因为「点外部关闭」
 * 每次手写都会漏掉一种情况（点在自己身上却冒泡到 document）。
 */

import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';

import './Popover.css';

export function Popover({
  open,
  onClose,
  title,
  width,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  width: number;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener('keydown', onKey);
    // capture 阶段之外再等一帧，避免打开浮层的那次点击立刻把它关掉
    const t = window.setTimeout(() => document.addEventListener('mousedown', onDown), 0);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onDown);
      window.clearTimeout(t);
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="pop" ref={ref} style={{ width }} role="dialog" aria-label={title}>
      <div className="pop__title">{title}</div>
      {children}
    </div>
  );
}
