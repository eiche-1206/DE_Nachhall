/* 顶栏。52px，**任何页面都不得出现第二排控件**。
 *
 * 右端预留 40px 头像位但**本期不渲染任何元素** —— 位置先占住，以后加
 * 用户系统时顶栏不会重新排版一次。
 *
 * 用 ⋯ 而不是齿轮：齿轮把这个位置钉死成设置入口，以后要加「删除本期」
 * 「导出字幕」就得再占一个图标位，而顶栏不许多东西。三点是「更多操作」，
 * 语义装得下设置以外的内容。
 */

import type { ReactNode } from 'react';

import './TopBar.css';

interface Props {
  /** 有值时左侧显示返回箭头 */
  onBack?: () => void;
  title: ReactNode;
  /** 右侧的进度指示，如 #11 / 27 */
  counter?: string;
  onImport?: () => void;
  onMore?: () => void;
  right?: ReactNode;
}

export function TopBar({ onBack, title, counter, onImport, onMore, right }: Props) {
  return (
    <header className="topbar">
      {onBack ? (
        <button className="topbar__icon" onClick={onBack} aria-label="返回">
          ←
        </button>
      ) : null}
      <div className="topbar__title">{title}</div>
      {counter ? <span className="topbar__counter tnum">{counter}</span> : null}
      {right}
      {onImport ? (
        <button className="topbar__icon" onClick={onImport} aria-label="导入素材">
          ＋
        </button>
      ) : null}
      {onMore ? (
        <button className="topbar__icon" onClick={onMore} aria-label="更多操作">
          ⋯
        </button>
      ) : null}
      {/* 头像位：占位不渲染 */}
      <span className="topbar__avatar-slot" aria-hidden="true" />
    </header>
  );
}
