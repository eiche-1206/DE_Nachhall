/* 听写输入。
 *
 * 写作过程中德语原文与中文翻译**均不可见**，本步骤也**不提供 S 字幕** ——
 * 看到原文等于直接看答案。
 *
 * 提交是 Enter，**提交即自动展示对照**，不需要再点一次。这一条写死不给
 * 开关：关掉它意味着每次听写完还要多点一次，那本身就是坏设计。
 */

import { useEffect, useRef } from 'react';

import './DictationPanel.css';

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
}

export function DictationPanel({ value, onChange, onSubmit }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    ref.current?.focus();
  }, []);

  return (
    <div className="dict">
      <textarea
        ref={ref}
        className="dict__input german"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          // Enter 提交；Shift+Enter 换行，德语长句偶尔需要
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            onSubmit();
          }
        }}
        placeholder="听到什么写什么，写不全也没关系。"
        spellCheck={false}
        aria-label="听写输入"
      />
    </div>
  );
}
