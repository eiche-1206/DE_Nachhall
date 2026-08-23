/* MediaRecorder 封装。
 *
 * 三条产品约束落在代码里：
 *   1. **正向计时，没有固定窗口**。用户手动结束（Enter 或按钮），
 *      180 秒兜底自动结束并 Toast。倒计时会逼人赶时间，而跟读要的是说清楚。
 *   2. **只显示已录时长，不显示任何参照值**。不给「原声 8.9s」之类的对照 ——
 *      那会让人去凑时长，而不是去说清楚。
 *   3. **不落盘、不上传**。切段时立刻 revokeObjectURL 释放，
 *      之前那条录音必须变得不可访问。
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export const RECORD_TIMEOUT_MS = 180_000;

export type MicState = 'idle' | 'recording' | 'denied' | 'unsupported';

export interface RecorderApi {
  state: MicState;
  /** 已录时长，毫秒。正向。 */
  elapsedMs: number;
  /** 回放用的 object URL。切段时会被释放并置空。 */
  url: string | null;
  start: () => void;
  stop: () => void;
  /** 切段时调用：停掉录音、释放 URL、清零计时 */
  reset: () => void;
  /** 麦克风被拒时的可操作提示 */
  error: string | null;
  /** 180 秒兜底触发过一次 */
  timedOut: boolean;
}

export function useRecorder(): RecorderApi {
  const [state, setState] = useState<MicState>('idle');
  const [elapsedMs, setElapsed] = useState(0);
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [timedOut, setTimedOut] = useState(false);

  const rec = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const stream = useRef<MediaStream | null>(null);
  const tick = useRef<number | null>(null);
  const guard = useRef<number | null>(null);
  const urlRef = useRef<string | null>(null);

  const clearTimers = useCallback(() => {
    if (tick.current !== null) window.clearInterval(tick.current);
    if (guard.current !== null) window.clearTimeout(guard.current);
    tick.current = null;
    guard.current = null;
  }, []);

  const releaseUrl = useCallback(() => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    urlRef.current = null;
    setUrl(null);
  }, []);

  const stopTracks = useCallback(() => {
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
  }, []);

  const stop = useCallback(() => {
    clearTimers();
    if (rec.current && rec.current.state !== 'inactive') rec.current.stop();
  }, [clearTimers]);

  const reset = useCallback(() => {
    stop();
    stopTracks();
    releaseUrl();
    setElapsed(0);
    setTimedOut(false);
    setState('idle');
  }, [stop, stopTracks, releaseUrl]);

  const start = useCallback(() => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setState('unsupported');
      setError('这个浏览器不支持录音。换 Chrome 或 Firefox 的新版本可以。');
      return;
    }

    releaseUrl();
    setElapsed(0);
    setTimedOut(false);
    setError(null);

    void navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((s) => {
        stream.current = s;
        chunks.current = [];
        const mr = new MediaRecorder(s);
        rec.current = mr;

        mr.ondataavailable = (e) => {
          if (e.data.size > 0) chunks.current.push(e.data);
        };
        mr.onstop = () => {
          clearTimers();
          stopTracks();
          const blob = new Blob(chunks.current, { type: mr.mimeType || 'audio/webm' });
          const next = URL.createObjectURL(blob);
          urlRef.current = next;
          setUrl(next);
          setState('idle');
        };

        mr.start();
        setState('recording');

        const t0 = performance.now();
        tick.current = window.setInterval(() => setElapsed(performance.now() - t0), 100);
        // 兜底：忘了按结束（去接了个电话）不该录满硬盘
        guard.current = window.setTimeout(() => {
          setTimedOut(true);
          if (rec.current && rec.current.state !== 'inactive') rec.current.stop();
        }, RECORD_TIMEOUT_MS);
      })
      .catch(() => {
        setState('denied');
        setError('麦克风被拒了。点地址栏左侧的图标，把麦克风改成「允许」，然后重试这一步。');
      });
  }, [clearTimers, releaseUrl, stopTracks]);

  // 卸载时必须释放：录音不落盘不上传，页面一走就该消失
  useEffect(
    () => () => {
      clearTimers();
      stopTracks();
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    },
    [clearTimers, stopTracks]
  );

  return { state, elapsedMs, url, start, stop, reset, error, timedOut };
}
