/* 处理中 / 失败的素材条，插在 HeroCard 与历史时间线之间。
 *
 * 失败态给两个出口，「仍然进入」是 PRD F3.1.2 那条验收标准的界面出口 ——
 * enriching 失败不阻塞跟读，转写已经完成的话段落照样能练。
 *
 * enriching 阶段用不确定态进度条：LLM 没有可观测进度，编一个百分比
 * 只会在 87% 卡住三十秒（PRD 约束 C4）。
 */

import type { MediaListItem } from '../lib/api';
import { Button } from './Button';
import { ProgressBar } from './ProgressBar';
import './IngestStrip.css';

const STAGE_LABEL: Record<string, string> = {
  queued: '排队中',
  downloading: '下载中',
  transcoding: '转码中',
  transcribing: '转写中',
  enriching: '生成章节与翻译',
};

/** 只有 enriching 是不确定态 —— 其余三步都有真实可测的进度。 */
const INDETERMINATE = new Set(['enriching', 'queued']);

export function IngestStrip({
  media,
  onRetry,
  onEnterAnyway,
}: {
  media: MediaListItem;
  onRetry: () => void;
  onEnterAnyway: () => void;
}) {
  const job = media.job;
  const failed = Boolean(job?.error_code);
  const stage = job?.stage ?? 'queued';
  const label = STAGE_LABEL[stage] ?? stage;

  return (
    <div className={`istrip${failed ? ' istrip--failed' : ''}`}>
      <span className="istrip__icon" aria-hidden="true">
        {failed ? '⚠' : '◌'}
      </span>
      <div className="istrip__body">
        <div className="istrip__title">{media.title}</div>
        {failed ? (
          <>
            <div className="istrip__note">
              失败于「{label}」· {job?.error_detail ?? '未知原因'}
            </div>
            <div className="istrip__actions">
              <Button size="sm" onClick={onRetry}>
                从该步重试
              </Button>
              <Button size="sm" onClick={onEnterAnyway}>
                仍然进入
              </Button>
            </div>
          </>
        ) : (
          <>
            <div className="istrip__note">{label}</div>
            <ProgressBar
              percent={INDETERMINATE.has(stage) ? null : (job?.percent ?? 0)}
              label={label}
            />
          </>
        )}
      </div>
    </div>
  );
}
