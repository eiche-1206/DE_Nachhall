/* 翻译折叠。
 *
 * **默认折叠** —— B2–C1 的学习者不该先看翻译。展开是主动动作，快捷键 T。
 *
 * 听写写作期**整个组件不渲染**（由调用方控制）：翻译也是答案的一部分。
 * enriching 未完成时整行灰掉不可点，而不是隐藏 —— 让人知道这东西存在、
 * 正在来的路上。
 */

import { useId } from 'react';

import './Disclosure.css';

interface Props {
  open: boolean;
  onToggle: () => void;
  /** null = 还在生成中 */
  text: string | null;
  label?: string;
}

export function Disclosure({ open, onToggle, text, label = '中文翻译' }: Props) {
  const id = useId();
  const pending = text === null;

  return (
    <div className="disc">
      <button
        className={`disc__head${pending ? ' disc__head--pending' : ''}`}
        onClick={pending ? undefined : onToggle}
        aria-expanded={pending ? undefined : open}
        aria-controls={id}
        aria-disabled={pending || undefined}
      >
        <span className="disc__caret" aria-hidden="true">
          {open && !pending ? '▾' : '▸'}
        </span>
        <span>{label}</span>
        {pending ? <span className="disc__pending">◌ 生成中</span> : null}
        <span className="disc__kbd">T</span>
      </button>
      {open && !pending ? (
        <div id={id} className="disc__body zh">
          {text}
        </div>
      ) : null}
    </div>
  );
}
