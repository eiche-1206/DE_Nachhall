/* 首页为空。一句话 + 指向 ＋ 的提示，**不放插画** —— 插画占掉的空间
 * 比它传达的信息值钱，而且第二次看到就只剩碍事。 */

import './EmptyState.css';

export function EmptyState({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="empty">
      <p className="empty__title">{title}</p>
      <p className="empty__hint">{hint}</p>
    </div>
  );
}
