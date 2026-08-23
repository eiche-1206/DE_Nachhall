/* 首页。
 *
 * **统一时间线**：订阅源与自导入混排，不分 Tab（PRD A9）。最新一期展开为
 * HeroCard，其余是紧凑行。处理中与失败的插在两者之间。
 *
 * **所有入口都直达回声闭环的 ① 播放原声**，不经过详情页 —— 首页的每一次
 * 点击都是「现在开始练」。章节与段落带 ?chunk= 直接落到那一段。
 * 详情页暂缓（见 UI-SPEC §6.2），路由还在，直接敲 URL 仍可访问。
 *
 * MVP 没有发现入口：内容从订阅来，或者自己贴链接。
 */

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { EmptyState } from '../components/EmptyState';
import { EpisodeRow } from '../components/EpisodeRow';
import { HeroCard } from '../components/HeroCard';
import { ImportSheet } from '../components/ImportSheet';
import { IngestStrip } from '../components/IngestStrip';
import { TopBar } from '../components/TopBar';
import { useToast } from '../components/Toast';
import { useIngestPolling } from '../hooks/useIngestPolling';
import { ApiError, api } from '../lib/api';
import type { ChapterOut, MediaListItem } from '../lib/api';
import './HomePage.css';

const READY = new Set(['ready', 'ready_partial']);

export function HomePage() {
  const nav = useNavigate();
  const { toast } = useToast();
  const { items, loading, error, refresh } = useIngestPolling();
  const [importOpen, setImportOpen] = useState(false);

  const ready = items.filter((m) => READY.has(m.status));
  const pending = items.filter((m) => !READY.has(m.status));
  const [hero, ...rest] = ready;

  // HeroCard 要显示章节，而列表接口刻意不带它们（首页只谈时长）
  const [heroChapters, setHeroChapters] = useState<ChapterOut[]>([]);
  const [heroPending, setHeroPending] = useState(false);

  useEffect(() => {
    if (!hero) return;
    let live = true;
    void api
      .media(hero.id)
      .then((d) => {
        if (!live) return;
        setHeroChapters(d.chapters);
        setHeroPending(d.chapters.length === 0);
      })
      .catch(() => {
        if (live) setHeroPending(true);
      });
    return () => {
      live = false;
    };
  }, [hero?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function retry(m: MediaListItem) {
    try {
      await api.retry(m.id);
      toast('已重新排队，从失败的那一步继续。');
      void refresh();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : '重试失败。', 'err');
    }
  }

  return (
    <div className="page">
      <TopBar title="DE_Nachhall" onImport={() => setImportOpen(true)} />
      <ImportSheet
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={(id, existed) => {
          setImportOpen(false);
          if (existed) {
            toast('这一期已在库中，已为你打开。');
            nav(`/episode/${id}/echo`);
          } else {
            toast('已加入队列。');
            void refresh();
          }
        }}
      />

      <main className="wrap-home home">
        {error ? <p className="home__error">{error}</p> : null}

        {!loading && items.length === 0 ? (
          <EmptyState title="还没有素材" hint="点右上角的 ＋ 贴一个视频链接开始。" />
        ) : null}

        {hero ? (
          <HeroCard
            media={hero}
            chapters={heroChapters}
            chaptersPending={heroPending}
            onOpen={() => nav(`/episode/${hero.id}/echo`)}
            onStart={() => nav(`/episode/${hero.id}/echo`)}
            onChapter={(chunkStart) => nav(`/episode/${hero.id}/echo?chunk=${chunkStart}`)}
          />
        ) : null}

        {pending.length ? (
          <section className="home__pending">
            {pending.map((m) => (
              <IngestStrip
                key={m.id}
                media={m}
                onRetry={() => void retry(m)}
                onEnterAnyway={() => nav(`/episode/${m.id}/echo`)}
              />
            ))}
          </section>
        ) : null}

        {rest.length ? (
          <section className="home__list">
            <h2 className="label home__list-title">往期</h2>
            <ul className="home__rows">
              {rest.map((m) => (
                <EpisodeRow key={m.id} media={m} onOpen={() => nav(`/episode/${m.id}/echo`)} />
              ))}
            </ul>
          </section>
        ) : null}
      </main>
    </div>
  );
}
