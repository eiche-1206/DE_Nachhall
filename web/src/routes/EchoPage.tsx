/* 回声闭环。全屏沉浸布局 + 可拉出侧栏。
 *
 * 三条布局硬规则（设计原则 3「不位移」）：
 *   字幕区 88px、状态行 48px、控制条 68px —— **在所有步骤中恒定**。
 *   内容多寡不影响高度，视频永远在同一个位置。
 *
 * 听写与对照溢出时**页面滚动，视频不缩小**。视频一旦在步骤间忽大忽小，
 * 跟读的节奏就断了。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';

import { ChunkList } from '../components/ChunkList';
import { ComparePanel } from '../components/ComparePanel';
import { DictationPanel } from '../components/DictationPanel';
import { Disclosure } from '../components/Disclosure';
import { RecFrame } from '../components/RecFrame';
import { SegmentBar } from '../components/SegmentBar';
import { SettingsPanel } from '../components/SettingsPanel';
import { StepBar } from '../components/StepBar';
import { useToast } from '../components/Toast';
import { TopBar } from '../components/TopBar';
import { Transport } from '../components/Transport';
import type { TransportAction } from '../components/Transport';
import { VideoStage } from '../components/VideoStage';
import { useEchoMachine } from '../echo/useEchoMachine';
import { useHotkeys } from '../echo/useHotkeys';
import { useRecorder } from '../echo/useRecorder';
import { useVideoStage } from '../echo/useVideoStage';
import { STEP_META } from '../echo/stepMeta';
import { ApiError, api, mediaUrl } from '../lib/api';
import type { ChapterOut, ChunkOut, MediaDetail } from '../lib/api';
import { shortDuration } from '../lib/format';
import { useSettings } from '../settings/SettingsProvider';
import { parseChunkIndex, parseMediaId } from './params';
import './EchoPage.css';

export function EchoPage() {
  const nav = useNavigate();
  const { id } = useParams();
  const { search } = useLocation();
  const mediaId = parseMediaId(id);
  const initialChunk = parseChunkIndex(search);

  const { settings } = useSettings();
  const { toast } = useToast();

  const [media, setMedia] = useState<MediaDetail | null>(null);
  const [chunks, setChunks] = useState<ChunkOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  // 默认展开：段落列表是导航面板，不是偶尔唤出的抽屉
  const [sidebar, setSidebar] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const machine = useEchoMachine(settings, initialChunk);
  const { state, step } = machine;
  const meta = STEP_META[step];

  // 连播时听写与录音不参与：这是「听一遍整期」，不是跟读
  const continuous = settings.continuousPlay;

  const recorder = useRecorder();
  const playbackRef = useRef<HTMLAudioElement>(null);

  const chunk: ChunkOut | undefined = chunks[state.chunkIdx];
  const chapters: ChapterOut[] = media?.chapters ?? [];

  // ---------- 数据 ----------

  useEffect(() => {
    if (mediaId === null) {
      setError('这个链接不对。');
      return;
    }
    let live = true;
    void Promise.all([api.media(mediaId), api.chunks(mediaId)])
      .then(([d, c]) => {
        if (!live) return;
        setMedia(d);
        setChunks(c.chunks);
      })
      .catch((e: unknown) => {
        if (live) setError(e instanceof ApiError ? e.message : '加载失败。');
      });
    return () => {
      live = false;
    };
  }, [mediaId]);

  // ---------- 播放 ----------

  // 走 ref：真正的处理要用到下面才定义的 gotoChunk，而 useVideoStage
  // 必须先于它建立。useVideoStage 内部本来也是每次渲染更新 ref。
  const spanEndRef = useRef<() => void>(() => {});
  const video = useVideoStage(() => spanEndRef.current());

  const playChunk = useCallback(() => {
    if (!chunk) return;
    video.play({ startMs: chunk.start_ms, endMs: chunk.end_ms });
  }, [chunk, video]);

  // 进入播放类步骤就自动开始 —— 每一步都要手动点一次会毁掉节奏
  useEffect(() => {
    if (!chunk) return;
    if (step === 'play1' || step === 'replay2') {
      playChunk();
    } else {
      video.stop();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, state.chunkIdx, chunk?.idx]);

  // 录音步骤：进来就开录，离开就停
  useEffect(() => {
    if (step === 'record') {
      recorder.start();
    } else if (recorder.state === 'recording') {
      recorder.stop();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  useEffect(() => {
    if (recorder.timedOut) toast('录音已达 180 秒上限，自动结束。');
  }, [recorder.timedOut, toast]);

  useEffect(() => {
    if (recorder.error) toast(recorder.error, 'err');
  }, [recorder.error, toast]);

  // 切段：**立刻释放上一段的录音**，不落盘不留存
  const gotoChunk = useCallback(
    (idx: number) => {
      if (idx < 0 || idx >= chunks.length) return;
      video.stop();
      recorder.reset();
      machine.gotoChunk(idx);
    },
    [chunks.length, machine, recorder, video]
  );

  // 播完往哪走。两条规则叠在一起：
  //   连播模式  —— ① 播完进**下一段**，继续播 ①，一路到底
  //   其余情况  —— 由步骤自己说了算（STEP_META.advanceOnSpanEnd）
  spanEndRef.current = () => {
    if (continuous && step === 'play1') {
      if (state.chunkIdx < chunks.length - 1) {
        gotoChunk(state.chunkIdx + 1);
      }
      // 最后一段播完就停在这儿，不自动跳去等待确认 —— 连播的终点是「放完了」
      return;
    }
    if (STEP_META[step].advanceOnSpanEnd) machine.next();
  };

  const playRecording = useCallback(() => {
    const el = playbackRef.current;
    if (!el || !recorder.url) return;
    el.currentTime = 0;
    void el.play();
  }, [recorder.url]);

  // ---------- Space / Enter 的语义随步骤走 ----------

  const onSpace = useCallback(() => {
    switch (step) {
      case 'play1':
      case 'replay2':
      case 'dictate':
        playChunk();
        break;
      case 'record':
        recorder.start(); // 重录
        break;
      case 'playback':
        playRecording();
        break;
      case 'confirm':
        machine.restart();
        break;
    }
  }, [machine, playChunk, playRecording, recorder, step]);

  const onEnter = useCallback(() => {
    if (step === 'dictate') {
      if (state.dictation === 'writing') machine.submitDictation();
      else machine.next();
      return;
    }
    if (step === 'record') {
      recorder.stop();
      machine.next();
      return;
    }
    machine.next();
  }, [machine, recorder, state.dictation, step]);

  const handlers = useMemo(
    () => ({
      onSpace,
      onEnter,
      onPrev: () => gotoChunk(state.chunkIdx - 1),
      onNext: () => gotoChunk(state.chunkIdx + 1),
      // ② 不提供 S —— 快捷键也一并禁掉，否则规则只在按钮上成立
      onSubtitles: meta.allowSubtitleToggle ? machine.toggleSubtitles : undefined,
      onTranslation: step === 'dictate' && state.dictation === 'writing'
        ? undefined
        : machine.toggleTranslation,
      onSidebar: () => setSidebar((v) => !v),
      // 详情页暂缓，← 与 Esc 都回首页
      onEscape: () => (sidebar ? setSidebar(false) : nav('/')),
    }),
    [
      gotoChunk, machine, meta.allowSubtitleToggle, nav, onEnter, onSpace,
      sidebar, state.chunkIdx, state.dictation, step,
    ]
  );

  useHotkeys(handlers, !settingsOpen);

  // ---------- 渲染 ----------

  if (error) {
    return (
      <div className="page">
        <TopBar title="DE_Nachhall" onBack={() => nav('/')} />
        <main className="wrap-content echo__error">{error}</main>
      </div>
    );
  }

  if (!media || !chunk) {
    return (
      <div className="page">
        <TopBar title="DE_Nachhall" onBack={() => nav('/')} />
        <main className="wrap-content echo__error">◌ 加载中…</main>
      </div>
    );
  }

  const chapter = chapters.find((c) => c.idx === chunk.chapter_idx);
  const writing = step === 'dictate' && state.dictation === 'writing';
  // 只看 state：textVisible 已经在进入这一步时决定了它的初值（见 useEchoMachine）
  const showText = state.subtitles && !writing;

  const actions: TransportAction[] = buildActions();

  return (
    <div className="page echo">
      <TopBar
        title={chapter?.title ?? media.title}
        counter={`#${chunk.idx + 1} / ${chunks.length}`}
        onBack={() => nav('/')}
        onMore={() => setSettingsOpen((v) => !v)}
        right={
          <button
            className="topbar__toggle"
            onClick={() => setSidebar((v) => !v)}
            title="段落列表（Tab）"
            aria-pressed={sidebar}
          >
            段落 <span className={`echo__tri${sidebar ? '' : ' echo__tri--out'}`} />
          </button>
        }
      />
      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />

      <div className="echo__body">
        {/* 左侧镜像留白：右边那列的对称项，视频因此落在页面正中 */}
        <div className="echo__gutter" aria-hidden="true" />

        <main className="echo__main">
          <VideoStage
            ref={video.ref}
            src={mediaUrl.stream(media.id)}
            timecode={`${shortDuration(video.positionMs)} / ${shortDuration(media.duration_ms ?? 0)}`}
          >
            <RecFrame active={recorder.state === 'recording'} elapsedMs={recorder.elapsedMs} />
          </VideoStage>

          {/* 段落导航条。点哪格跳哪段 —— 不能自由拖动，见组件注释。
              关掉时整个不渲染，**不留占位** —— 下面的内容会上移 14px。
              这不违反「任何状态下尺寸与位置都不变」：那条约束的是**步骤切换**，
              而这里是用户自己拨了开关，位置变化正是他要的结果。 */}
          {settings.segmentBar ? (
            <SegmentBar
              chunks={chunks}
              currentIdx={chunk.idx}
              positionMs={video.positionMs}
              onPick={gotoChunk}
            />
          ) : null}

          {/* 88px 恒定 —— 有没有文字都占这么高 */}
          <div className="echo__subs">
            {showText ? <p className="german">{chunk.text}</p> : null}
          </div>

          {/* 26px 恒定。步骤条同时报当前位置、说明这一步做什么、并且可跳转。 */}
          <div className="echo__status">
            <StepBar
              steps={state.steps}
              pos={state.stepPos}
              note={continuous && step === 'play1' ? '连播中 · 播完自动进下一段' : undefined}
              onPick={machine.gotoStep}
            />
          </div>

          {/* 68px 恒定 */}
          <Transport actions={actions} />

          {/* 听写与对照溢出时页面滚动，视频不缩小 */}
          {writing ? (
            <DictationPanel
              value={state.draft}
              onChange={machine.setDraft}
              onSubmit={machine.submitDictation}
            />
          ) : null}

          {step === 'dictate' && state.dictation === 'comparing' ? (
            <ComparePanel mine={state.draft} original={chunk.text} />
          ) : null}

          {/* 写作期整个 Disclosure 不渲染 —— 翻译也是答案的一部分 */}
          {!writing ? (
            <Disclosure
              open={state.translationOpen}
              onToggle={machine.toggleTranslation}
              text={chunk.translation_zh ?? null}
            />
          ) : null}
        </main>

        {sidebar ? (
          <aside className="echo__side">
            <div className="echo__side-head">
              <span>段落 · {chunks.length}</span>
              <button
                className="echo__side-close"
                onClick={() => setSidebar(false)}
                title="收起段落列表（Tab）"
                aria-label="收起段落列表"
              >
                <span className="echo__tri" />
              </button>
            </div>
            <div className="echo__side-scroll">
              <ChunkList
                chunks={chunks}
                chapters={chapters}
                currentIdx={chunk.idx}
                variant="sidebar"
                onPick={gotoChunk}
              />
            </div>
            <div className="echo__side-foot">点任意一段，从那一段开始回声</div>
          </aside>
        ) : (
          /* 收起时这一列仍然占着，视频因此一动不动 */
          <div className="echo__side echo__side--empty" aria-hidden="true" />
        )}

        {sidebar ? null : (
          <button
            className="echo__handle"
            onClick={() => setSidebar(true)}
            title="段落列表（Tab）"
            aria-label="展开段落列表"
          >
            <span className="echo__tri echo__tri--out" />
          </button>
        )}
      </div>

      {/* 回放用独立 audio 元素，不动视频 —— 视频要停在该帧 */}
      <audio ref={playbackRef} src={recorder.url ?? undefined} hidden />
    </div>
  );

  function buildActions(): TransportAction[] {
    // 这一对镜像对称：箭头徽章各自指向外侧，位置本身就在说方向。
    // 徽章在**每一步都在** —— 之前有几步把 next 的徽章去掉了，
    // 同一个键时有时无，人只会以为这一步按 → 没用。
    const prev: TransportAction = {
      key: 'prev',
      label: '上一段',
      kbd: '←',
      kbdSide: 'start',
      onClick: () => gotoChunk(state.chunkIdx - 1),
      disabled: state.chunkIdx === 0,
    };
    const next: TransportAction = {
      key: 'next',
      label: '下一段',
      kbd: '→',
      onClick: () => gotoChunk(state.chunkIdx + 1),
      disabled: state.chunkIdx >= chunks.length - 1,
    };
    const subs: TransportAction = {
      key: 'subs',
      label: state.subtitles ? 'S 隐藏字幕' : 'S 字幕',
      onClick: machine.toggleSubtitles,
    };
    const trans: TransportAction = {
      key: 'trans',
      label: 'T 翻译',
      onClick: machine.toggleTranslation,
    };

    switch (step) {
      case 'play1':
      case 'replay2':
        return [
          { key: 'again', label: '↺ 再听原声', kbd: 'Space', variant: 'ghost-accent', onClick: onSpace },
          prev, next, subs, trans,
        ];
      case 'dictate':
        return state.dictation === 'writing'
          ? [
              { key: 'again', label: '▶ 再听一遍', kbd: 'Space', variant: 'ghost-accent', onClick: playChunk },
              { key: 'submit', label: '提交', kbd: 'Enter', variant: 'primary', onClick: machine.submitDictation },
              prev,
              next,
            ]
          : [
              { key: 'rewrite', label: '✎ 重写', onClick: machine.rewrite },
              { key: 'again', label: '▶ 再听一遍', kbd: 'Space', variant: 'ghost-accent', onClick: playChunk },
              { key: 'go', label: '继续 →', kbd: 'Enter', variant: 'primary', onClick: machine.next },
              // 对照期原文已经摊开了，翻译不再是「答案」；写作期仍然不给
              trans,
            ];
      case 'record':
        return [
          { key: 'stop', label: '■ 结束录音', kbd: 'Enter', variant: 'primary', onClick: onEnter },
          { key: 'redo', label: '↺ 重录', kbd: 'Space', variant: 'ghost-accent', onClick: recorder.start },
          prev,
          next,
          subs,
        ];
      case 'playback':
        // 不给单独的「▶ 我的」—— 那就是 Space 本身，两个入口做同一件事只会让人怀疑它们不同
        return [
          { key: 'again', label: '↺ 回放录音', kbd: 'Space', variant: 'ghost-accent', onClick: playRecording },
          { key: 'orig', label: '▶ 原声', onClick: playChunk },
          prev,
          next,
          subs,
        ];
      case 'confirm':
        return [
          { key: 'restart', label: '↺ 从头再来', kbd: 'Space', variant: 'ghost-accent', onClick: machine.restart },
          { key: 'orig', label: '▶ 原声', onClick: playChunk },
          ...(recorder.url ? [{ key: 'mine', label: '▶ 我的', onClick: playRecording }] : []),
          prev, next,
        ];
    }
  }
}
