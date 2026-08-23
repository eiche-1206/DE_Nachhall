/* 处理中素材的 2 秒轮询。
 *
 * 阶段状态存在数据库里（不是 Redis），所以前端直接读 /api/media 就够了 ——
 * 这正是 SPEC 拒绝引入 Redis 的原因：多一处状态就多一次双写。
 *
 * **没有处理中的项就不轮询。** 空转会让笔记本风扇一直响。
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError, api } from '../lib/api';
import type { MediaListItem } from '../lib/api';

const INTERVAL_MS = 2000;
const ACTIVE = new Set(['queued', 'processing']);

export function useIngestPolling() {
  const [items, setItems] = useState<MediaListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await api.timeline();
      setItems(r.items);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '加载失败。');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const hasActive = items.some((m) => ACTIVE.has(m.status));

  useEffect(() => {
    if (!hasActive) return;
    timer.current = window.setInterval(() => void refresh(), INTERVAL_MS);
    return () => {
      if (timer.current !== null) window.clearInterval(timer.current);
    };
  }, [hasActive, refresh]);

  return { items, loading, error, refresh, setItems };
}
