/* localStorage 实现。
 *
 * 读失败**一律回落默认值，绝不抛错** —— 隐私模式、清缓存、跨浏览器同步
 * 写坏了，任何一种都不该让整个应用白屏。设置丢了最多是回到默认预设。
 */

import type { Settings, SettingsProvider } from './types';
import { DEFAULT_SETTINGS } from './types';

const KEY = 'de_nachhall.settings.v1';

function coerce(raw: unknown): Settings {
  if (typeof raw !== 'object' || raw === null) return DEFAULT_SETTINGS;
  const src = raw as Record<string, unknown>;
  const out = { ...DEFAULT_SETTINGS };
  for (const k of Object.keys(DEFAULT_SETTINGS) as (keyof Settings)[]) {
    if (typeof src[k] === 'boolean') out[k] = src[k] as boolean;
  }
  return out;
}

export const localStorageSettings: SettingsProvider = {
  read() {
    try {
      const raw = window.localStorage.getItem(KEY);
      return raw ? coerce(JSON.parse(raw)) : DEFAULT_SETTINGS;
    } catch {
      return DEFAULT_SETTINGS;
    }
  },

  write(next) {
    try {
      window.localStorage.setItem(KEY, JSON.stringify(next));
    } catch {
      /* 隐私模式下写不进去。设置在本次会话内仍然生效，只是不持久。 */
    }
  },
};
