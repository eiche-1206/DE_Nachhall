/* 五步状态机。前端最复杂的一块。
 *
 * 核心是把四个 settings 布尔翻译成步骤序列。三条硬要求：
 *
 *   1. **关闭的步骤完全跳过，不产生界面闪现。** 序列在进入这一段之前就
 *      算好，运行时不再判断「这一步要不要跳」—— 那样必然会先渲染一帧
 *      再跳走。
 *   2. **record 一个开关同时驱动 ③④⑤。** 二次播放是录音前的准备动作，
 *      回放是录音后的对比动作，两者都没有独立存在的理由 —— 关掉录音还
 *      单独留着「重听一遍然后什么也不做」是假选择。设置 2 个开关对运行时
 *      最多 6 步，这是有意的非一一对应。
 *   3. **全部关闭时退化为「播放原声 + 等待确认」。** 闭环仍然成立，
 *      只是最短。等待态**不自动推进** —— 什么时候进下一段是用户的决定。
 */

import { useCallback, useEffect, useMemo, useReducer } from 'react';

import type { Settings } from '../settings/types';
import { STEP_META } from './stepMeta';
import type { DictationPhase, EchoState, StepId } from './types';

export function buildSteps(s: Settings): StepId[] {
  const steps: StepId[] = ['play1'];
  if (s.dictation) steps.push('dictate');
  // 一个开关，三步：录音前先自动重听一遍并展示原文，录完立即回放
  if (s.record) steps.push('replay2', 'record', 'playback');
  steps.push('confirm');
  return steps;
}

/** 进某一步时字幕默认可见吗。
 *
 * 这一层是 S 那个 bug 的根源：原来写的是
 *     showText = meta.textVisible || state.subtitles
 * `||` 在 ③④⑤⑥ 被 textVisible=true 短路，state.subtitles 根本不参与，
 * 于是那四步按 S 毫无反应，而按钮还写着「S 隐藏字幕」。
 * 现在 textVisible 只决定**进这一步时的默认值**，可见性由 state 说了算。
 */
function defaultSubs(step: StepId | undefined, pref: boolean): boolean {
  if (!step) return pref;
  return STEP_META[step].textVisible || pref;
}

type Action =
  | { type: 'next' }
  | { type: 'prev' }
  | { type: 'restart' }
  | { type: 'gotoStep'; pos: number }
  | { type: 'gotoChunk'; idx: number }
  | { type: 'setSteps'; steps: StepId[] }
  | { type: 'setDraft'; text: string }
  | { type: 'setDictation'; phase: DictationPhase }
  | { type: 'toggleSubtitles' }
  | { type: 'toggleTranslation' };

/** 换步骤。字幕回到新步骤的默认值 —— 在 ③ 手动关掉的字幕，
 *  不该跟着带进 ④，因为两步的默认语义本来就不同。 */
function moveTo(state: EchoState, pos: number): EchoState {
  return {
    ...state,
    stepPos: pos,
    dictation: 'writing',
    subtitles: defaultSubs(state.steps[pos], state.prefSubtitles),
  };
}

/** 换段时重置的部分。草稿不跨段保留 —— 那是上一段的答案。 */
function freshForChunk(state: EchoState, chunkIdx: number): EchoState {
  return {
    ...state,
    chunkIdx,
    stepPos: 0,
    dictation: 'writing',
    draft: '',
    translationOpen: false,
    subtitles: defaultSubs(state.steps[0], state.prefSubtitles),
  };
}

function reducer(state: EchoState, action: Action): EchoState {
  switch (action.type) {
    case 'next': {
      const last = state.steps.length - 1;
      // 等待确认是终点，不自动推进；进下一段由 gotoChunk 显式触发
      if (state.stepPos >= last) return state;
      return moveTo(state, state.stepPos + 1);
    }
    case 'prev':
      if (state.stepPos <= 0) return state;
      return moveTo(state, state.stepPos - 1);
    case 'restart':
      return moveTo(state, 0);
    case 'gotoStep': {
      // 直接跳到任意一步。允许往回跳，也允许跳过没做的步骤 ——
      // 这是训练工具不是流程审批，顺序是建议不是约束。
      const pos = Math.max(0, Math.min(action.pos, state.steps.length - 1));
      if (pos === state.stepPos) return state;
      return moveTo(state, pos);
    }
    case 'gotoChunk':
      return freshForChunk(state, action.idx);
    case 'setSteps': {
      // settings 中途改了：序列重算，位置钳到新序列范围内
      const stepPos = Math.min(state.stepPos, action.steps.length - 1);
      return {
        ...state,
        steps: action.steps,
        stepPos,
        subtitles: defaultSubs(action.steps[stepPos], state.prefSubtitles),
      };
    }
    case 'setDraft':
      return { ...state, draft: action.text };
    case 'setDictation':
      return { ...state, dictation: action.phase };
    case 'toggleSubtitles':
      return { ...state, subtitles: !state.subtitles };
    case 'toggleTranslation':
      return { ...state, translationOpen: !state.translationOpen };
  }
}

export interface EchoMachine {
  state: EchoState;
  step: StepId;
  isLast: boolean;
  next: () => void;
  prev: () => void;
  restart: () => void;
  gotoStep: (pos: number) => void;
  gotoChunk: (idx: number) => void;
  setDraft: (text: string) => void;
  submitDictation: () => void;
  rewrite: () => void;
  toggleSubtitles: () => void;
  toggleTranslation: () => void;
}

export function useEchoMachine(settings: Settings, initialChunk: number): EchoMachine {
  const steps = useMemo(() => buildSteps(settings), [settings]);

  const [state, dispatch] = useReducer(reducer, undefined, (): EchoState => ({
    chunkIdx: initialChunk,
    steps,
    stepPos: 0,
    dictation: 'writing',
    draft: '',
    subtitles: defaultSubs(steps[0], settings.subtitles),
    prefSubtitles: settings.subtitles,
    translationOpen: false,
  }));

  // settings 在浮层里改了：序列立刻跟着变，不等下一段
  useEffect(() => {
    dispatch({ type: 'setSteps', steps });
  }, [steps]);

  const step = state.steps[state.stepPos] ?? 'play1';

  return {
    state,
    step,
    isLast: state.stepPos >= state.steps.length - 1,
    next: useCallback(() => dispatch({ type: 'next' }), []),
    prev: useCallback(() => dispatch({ type: 'prev' }), []),
    restart: useCallback(() => dispatch({ type: 'restart' }), []),
    gotoStep: useCallback((pos: number) => dispatch({ type: 'gotoStep', pos }), []),
    gotoChunk: useCallback((idx: number) => dispatch({ type: 'gotoChunk', idx }), []),
    setDraft: useCallback((text: string) => dispatch({ type: 'setDraft', text }), []),
    // 提交即自动展示对照，不需要再点一次
    submitDictation: useCallback(() => dispatch({ type: 'setDictation', phase: 'comparing' }), []),
    rewrite: useCallback(() => dispatch({ type: 'setDictation', phase: 'writing' }), []),
    toggleSubtitles: useCallback(() => dispatch({ type: 'toggleSubtitles' }), []),
    toggleTranslation: useCallback(() => dispatch({ type: 'toggleTranslation' }), []),
  };
}
