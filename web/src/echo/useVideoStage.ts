/* 精确播放一段：seek 到 chunk.start，在 chunk.end 自动暂停。
 *
 * **暂停判定必须走 requestVideoFrameCallback**（UI-SPEC §5.6，实测见
 * docs/sprint0-v2b-report.md）：
 *
 *                 Chrome 131        Firefox 136      预算
 *     rVFC        P95  39.5 ms      P95  78.7 ms     200 ms
 *     timeupdate  P95 251.0 ms      P95 277.5 ms     200 ms
 *                 中位 170.1 ms     中位 205.6 ms  ← 中位数就超标
 *
 * 单靠 timeupdate：Chrome 上每五段有一段超标，Firefox 上一半以上的段落
 * 会在超标点暂停。Firefox 早期版本没有 rVFC，回落 rAF —— 它的粒度同样
 * 是一帧，只是拿不到呈现时间戳，对「什么时候该停」这件事够用。
 *
 * 暂停后**画面停在该帧**：只调 pause() 不改 currentTime，不黑屏不跳回。
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export interface Span {
  startMs: number;
  endMs: number;
}

type Frame = { cancel: () => void };

/** rVFC 优先，没有就退 rAF。两者的粒度都是一帧，timeupdate 不在选项里。 */
function everyFrame(video: HTMLVideoElement, fn: () => void): Frame {
  const rvfc = (
    video as HTMLVideoElement & {
      requestVideoFrameCallback?: (cb: () => void) => number;
      cancelVideoFrameCallback?: (id: number) => void;
    }
  ).requestVideoFrameCallback;

  if (typeof rvfc === 'function') {
    let id = 0;
    let live = true;
    const loop = () => {
      if (!live) return;
      fn();
      if (live) id = rvfc.call(video, loop);
    };
    id = rvfc.call(video, loop);
    return {
      cancel: () => {
        live = false;
        (
          video as HTMLVideoElement & { cancelVideoFrameCallback?: (i: number) => void }
        ).cancelVideoFrameCallback?.(id);
      },
    };
  }

  let raf = 0;
  const loop = () => {
    fn();
    raf = window.requestAnimationFrame(loop);
  };
  raf = window.requestAnimationFrame(loop);
  return { cancel: () => window.cancelAnimationFrame(raf) };
}

export interface VideoStageApi {
  ref: React.RefObject<HTMLVideoElement>;
  /** 播放指定区间。已经在播则先停再重来。 */
  play: (span: Span) => void;
  /** 停在当前帧，不改 currentTime */
  stop: () => void;
  playing: boolean;
  /** 当前播放位置，毫秒。给时码叠层用。 */
  positionMs: number;
}

export function useVideoStage(onSpanEnd?: () => void): VideoStageApi {
  const ref = useRef<HTMLVideoElement>(null);
  const frame = useRef<Frame | null>(null);
  const endMs = useRef<number>(Number.POSITIVE_INFINITY);
  const onEnd = useRef(onSpanEnd);
  const [playing, setPlaying] = useState(false);
  const [positionMs, setPositionMs] = useState(0);

  onEnd.current = onSpanEnd;

  const stopWatch = useCallback(() => {
    frame.current?.cancel();
    frame.current = null;
  }, []);

  const stop = useCallback(() => {
    stopWatch();
    const v = ref.current;
    if (v && !v.paused) v.pause(); // 只暂停，不动 currentTime —— 画面留在该帧
    setPlaying(false);
  }, [stopWatch]);

  const play = useCallback(
    (span: Span) => {
      const v = ref.current;
      if (!v) return;
      stopWatch();
      endMs.current = span.endMs;

      const start = () => {
        void v.play().catch(() => setPlaying(false));
        setPlaying(true);
        frame.current = everyFrame(v, () => {
          const now = v.currentTime * 1000;
          setPositionMs(now);
          if (now >= endMs.current) {
            stopWatch();
            v.pause();
            setPlaying(false);
            onEnd.current?.();
          }
        });
      };

      // seek 完成后再播。已经落位的话（重复播同一段的开头）直接开始。
      const target = span.startMs / 1000;
      if (Math.abs(v.currentTime - target) < 0.02) {
        start();
      } else {
        const once = () => {
          v.removeEventListener('seeked', once);
          start();
        };
        v.addEventListener('seeked', once);
        v.currentTime = target;
      }
    },
    [stopWatch]
  );

  useEffect(() => stopWatch, [stopWatch]);

  return { ref, play, stop, playing, positionMs };
}
