/* 时间与日期的显示格式。集中一处，免得同一个时长在三个地方长得不一样。 */

/** 09:38 / 1:02:30。首页与详情页的时长。 */
export function duration(ms: number | null | undefined): string {
  if (!ms || ms < 0) return '--:--';
  const total = Math.round(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(h ? m : m).padStart(2, '0');
  const ss = String(s).padStart(2, '0');
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

/** 2:08。章节与段落的短时长，不补零到两位分钟。 */
export function shortDuration(ms: number): string {
  const total = Math.round(ms / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

/** 录音计时：< 60s 显示 3.4s，>= 60s 显示 1:04.2。只显示已录时长。 */
export function recTime(ms: number): string {
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rest = s - m * 60;
  return `${m}:${rest < 10 ? '0' : ''}${rest.toFixed(1)}`;
}

/** 2026-07-14。HeroCard 用全日期。 */
export function isoDate(d: string | null | undefined): string {
  return d ?? '';
}

/** 07-12。时间线行用短日期，年份在这个语境里是噪音。 */
export function shortDate(d: string | null | undefined): string {
  return d ? d.slice(5) : '--';
}
