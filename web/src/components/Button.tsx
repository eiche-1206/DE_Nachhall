/* 四变体两尺寸，可挂快捷键徽章。
 *
 * 硬规则：徽章里的键名**写文字不写符号** —— `Enter` 不是 `⏎`，`Space` 不是 `␣`。
 * 10px 下符号辨识不出，且不同平台字形差异大。方向键是唯一例外，
 * `→` 比 `ArrowRight` 好读。
 */

import type { ButtonHTMLAttributes, ReactNode } from 'react';

import './Button.css';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost-accent' | 'danger';
export type ButtonSize = 'sm' | 'md';

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** 快捷键提示，如 "Enter"、"Space"、"→" */
  kbd?: string;
  /**
   * 徽章放文字前还是文字后，默认后。
   *
   * 「上一段」「下一段」这一对要**镜像对称**：箭头各自指向外侧，
   * 徽章的位置本身就在说方向。所以前者用 start，后者用 end。
   */
  kbdSide?: 'start' | 'end';
  children: ReactNode;
}

export function Button({
  variant = 'secondary',
  size = 'md',
  kbd,
  kbdSide = 'end',
  children,
  className,
  type = 'button',
  ...rest
}: Props) {
  return (
    <button
      type={type}
      className={['btn', `btn--${variant}`, `btn--${size}`, className].filter(Boolean).join(' ')}
      {...rest}
    >
      {kbd && kbdSide === 'start' ? <kbd className="btn__kbd">{kbd}</kbd> : null}
      <span className="btn__label">{children}</span>
      {kbd && kbdSide === 'end' ? <kbd className="btn__kbd">{kbd}</kbd> : null}
    </button>
  );
}
