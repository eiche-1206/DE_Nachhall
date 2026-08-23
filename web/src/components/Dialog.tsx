/* 仅用于删除确认。**列出将被删除的内容** —— 只问「确定吗」等于没问。 */

import { useEffect } from 'react';
import type { ReactNode } from 'react';

import { Button } from './Button';
import './Dialog.css';

export function Dialog({
  open,
  title,
  onCancel,
  onConfirm,
  confirmLabel = '删除',
  children,
}: {
  open: boolean;
  title: string;
  onCancel: () => void;
  onConfirm: () => void;
  confirmLabel?: string;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div className="dlg__scrim" onMouseDown={onCancel}>
      <div
        className="dlg"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2 className="h2">{title}</h2>
        <div className="dlg__body">{children}</div>
        <div className="dlg__foot">
          <Button onClick={onCancel}>取消</Button>
          <Button variant="danger" onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
