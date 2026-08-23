/* 段落列表。两种语境，规格不同但同一个组件。
 *
 *   侧栏（回声页）  章节标题 + 单行省略；**不显示段数与时长** ——
 *                   正在训练，不需要盘点
 *   详情页          章节标题 + 段数 · 时长 + 两行省略
 *
 * **详情页是唯一显示段数的列表页。** 首页只谈时长（挑今天练什么），
 * 详情页才谈段数（看内部结构）。
 *
 * 侧栏里的德语原文本身就是字幕，听写写作期**也照常显示**（UI-SPEC §5.5）。
 * 这是有意保留的「偷看」通道，不是遗漏 —— 做过打码版本，明确决定不要。
 * 想不看就把侧栏收起来，那是用户自己的选择。
 */

import { useEffect, useRef } from 'react';

import type { ChapterOut, ChunkOut } from '../lib/api';
import { shortDuration } from '../lib/format';
import './ChunkList.css';

interface Props {
  chunks: ChunkOut[];
  chapters: ChapterOut[];
  currentIdx?: number;
  variant: 'sidebar' | 'detail';
  onPick: (chunkIdx: number) => void;
}

export function ChunkList({ chunks, chapters, currentIdx, variant, onPick }: Props) {
  const currentRef = useRef<HTMLLIElement>(null);

  useEffect(() => {
    currentRef.current?.scrollIntoView({ block: 'nearest' });
  }, [currentIdx]);

  // 未分章（ready_partial 或 LLM 降级）时平铺，不造假章节头
  const groups = chapters.length
    ? chapters.map((ch) => ({ chapter: ch, items: chunks.filter((c) => c.chapter_idx === ch.idx) }))
    : [{ chapter: null, items: chunks }];

  return (
    <div className={`clist clist--${variant}`}>
      {groups.map((g, gi) => (
        <section key={g.chapter?.idx ?? gi} className="clist__group">
          {g.chapter ? (
            <header className="clist__head">
              <span className="label clist__title">
                {String(g.chapter.idx + 1).padStart(2, '0')} {g.chapter.title}
              </span>
              {variant === 'detail' ? (
                <span className="clist__stat tnum">
                  {g.items.length} 段 · {shortDuration(g.chapter.end_ms - g.chapter.start_ms)}
                </span>
              ) : null}
            </header>
          ) : null}
          <ul>
            {g.items.map((c) => {
              const active = c.idx === currentIdx;
              return (
                <li key={c.idx} ref={active ? currentRef : undefined}>
                  <button
                    className={`clist__row${active ? ' clist__row--active' : ''}`}
                    onClick={() => onPick(c.idx)}
                    aria-current={active ? 'true' : undefined}
                  >
                    <span className="clist__num tnum">#{c.idx + 1}</span>
                    <span className="clist__text">{c.text}</span>
                    {variant === 'detail' ? (
                      <span className="clist__play" aria-hidden="true">
                        ▶
                      </span>
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
