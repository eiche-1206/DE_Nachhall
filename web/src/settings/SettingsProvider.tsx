/* 设置的唯一读写口。
 *
 * 调用点一律走 useSettings()，**不直接碰 localStorage** —— 否则换持久化
 * 方案时要满仓库找 key 名，而且没人保证每处都做了失败回落。
 */

import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import { localStorageSettings } from './localStorage';
import type { Settings, SettingsKey, SettingsProvider as Store } from './types';

interface Ctx {
  settings: Settings;
  set: (key: SettingsKey, value: boolean) => void;
  toggle: (key: SettingsKey) => void;
}

const SettingsContext = createContext<Ctx | null>(null);

export function SettingsProvider({
  children,
  store = localStorageSettings,
}: {
  children: ReactNode;
  store?: Store;
}) {
  const [settings, setSettings] = useState<Settings>(() => store.read());

  const set = useCallback(
    (key: SettingsKey, value: boolean) => {
      setSettings((prev) => {
        if (prev[key] === value) return prev;
        const next = { ...prev, [key]: value };
        store.write(next);
        return next;
      });
    },
    [store]
  );

  const toggle = useCallback(
    (key: SettingsKey) => {
      setSettings((prev) => {
        const next = { ...prev, [key]: !prev[key] };
        store.write(next);
        return next;
      });
    },
    [store]
  );

  const value = useMemo(() => ({ settings, set, toggle }), [settings, set, toggle]);
  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings(): Ctx {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error('useSettings 必须在 <SettingsProvider> 内使用');
  return ctx;
}
