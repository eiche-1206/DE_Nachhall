/* 键盘。这个产品是键盘优先的，鼠标是备选。
 *
 *   Space  重复当前这一步 —— 五个步骤里含义各不相同，所以按钮文案
 *          必须随步骤走（见 Transport 注释）
 *   Enter  结束录音 / 提交听写 / 继续
 *   ← →    切段
 *   S      字幕（语义随步骤反转，② 不提供）
 *   T      翻译
 *   Tab    侧栏
 *   Esc    返回
 *
 * 两条必须做对的细节：
 *   1. **Space 要 preventDefault**，否则浏览器翻页，视频跳走。
 *   2. **textarea 聚焦时只放行 Enter 与 Esc**，其余按键交给输入本身 ——
 *      否则打 s、t 会触发字幕和翻译，德语里这两个字母到处都是。
 */

import { useEffect } from 'react';

export interface HotkeyHandlers {
  onSpace?: () => void;
  onEnter?: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  onSubtitles?: () => void;
  onTranslation?: () => void;
  onSidebar?: () => void;
  onEscape?: () => void;
}

function inTextField(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  return (
    el.tagName === 'TEXTAREA' ||
    el.tagName === 'INPUT' ||
    el.isContentEditable
  );
}

export function useHotkeys(handlers: HotkeyHandlers, enabled = true): void {
  useEffect(() => {
    if (!enabled) return;

    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      const typing = inTextField(e.target);

      if (e.key === 'Escape') {
        // Esc 在输入框里也生效：它是退出焦点的唯一可靠出路
        if (typing && e.target instanceof HTMLElement) e.target.blur();
        handlers.onEscape?.();
        return;
      }

      if (e.key === 'Enter') {
        if (typing) return; // textarea 自己处理提交，见 DictationPanel
        e.preventDefault();
        handlers.onEnter?.();
        return;
      }

      // 输入中：字母、空格、方向键全部归输入本身
      if (typing) return;

      switch (e.key) {
        case ' ':
          e.preventDefault(); // 不拦就翻页
          handlers.onSpace?.();
          break;
        case 'ArrowLeft':
          e.preventDefault();
          handlers.onPrev?.();
          break;
        case 'ArrowRight':
          e.preventDefault();
          handlers.onNext?.();
          break;
        case 'Tab':
          e.preventDefault();
          handlers.onSidebar?.();
          break;
        default:
          switch (e.key.toLowerCase()) {
            case 's':
              handlers.onSubtitles?.();
              break;
            case 't':
              handlers.onTranslation?.();
              break;
          }
      }
    };

    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [enabled, handlers]);
}
