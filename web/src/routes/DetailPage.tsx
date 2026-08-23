/* 详情页。播放器 + 章节段落列表。
 *
 * **这是唯一显示段数的列表页。** 首页只谈时长（挑今天练什么），
 * 详情页才谈段数（看内部结构）。
 *
 * **ready_partial 时跟读照常可用**：章节头显示「生成中」，chunk 平铺
 * 不分组，进入回声闭环的入口不禁用。转写完成即可跟读，不必等 LLM。
 */

import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { Button } from '../components/Button';
import { ChunkList } from '../components/ChunkList';
import { SourceBadge } from '../components/SourceBadge';
import { TopBar } from '../components/TopBar';
import { VideoStage } from '../components/VideoStage';
import { ApiError, api, mediaUrl } from '../lib/api';
import type { ChunkOut, MediaDetail } from '../lib/api';
import { duration, isoDate } from '../lib/format';
import { parseMediaId } from './params';
import './DetailPage.css';

export function DetailPage() {
  const nav = useNavigate();
  const { id } = useParams();
  const mediaId = parseMediaId(id);

  const [media, setMedia] = useState<MediaDetail | null>(null);
  const [chunks, setChunks] = useState<ChunkOut[]>([]);
  const [error, setError] = useState<string | null>(null);

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

  if (error) {
    return (
      <div className="page">
        <TopBar title="DE_Nachhall" onBack={() => nav('/')} />
        <main className="wrap-content detail__error">{error}</main>
      </div>
    );
  }

  if (!media || mediaId === null) {
    return (
      <div className="page">
        <TopBar title="DE_Nachhall" onBack={() => nav('/')} />
        <main className="wrap-content detail__error">◌ 加载中…</main>
      </div>
    );
  }

  const partial = media.status === 'ready_partial';
  const playable = media.status === 'ready' || partial;

  return (
    <div className="page">
      <TopBar title={media.title} onBack={() => nav('/')} />

      <main className="wrap-content detail">
        <div className="detail__meta">
          <span className="detail__date tnum">{isoDate(media.published_on)}</span>
          <SourceBadge origin={media.origin} />
          <span className="meta">{duration(media.duration_ms)}</span>
          <span className="meta">{media.chunk_count} 段</span>
        </div>

        {playable ? <VideoStage src={mediaUrl.stream(media.id)} /> : null}

        <div className="detail__actions">
          <Button
            variant="primary"
            onClick={() => nav(`/episode/${media.id}/echo`)}
            disabled={!chunks.length}
          >
            ▶ 开始跟读
          </Button>
          {partial ? (
            <span className="meta">◌ 章节与翻译还在生成 · 跟读现在就能用</span>
          ) : null}
        </div>

        <ChunkList
          chunks={chunks}
          chapters={media.chapters}
          variant="detail"
          onPick={(idx) => nav(`/episode/${media.id}/echo?chunk=${idx}`)}
        />
      </main>
    </div>
  );
}
