/* 方框标签，**各处同一套规格**，不按容器分化。
 *
 * 同一个东西在 HeroCard、列表、详情页长得一样，扫视时才形成稳定的
 * 「来源列」。方框本身已经把徽章从周围文字里区隔出来了。
 *
 * 颜色编码的是**行为差异**，不是装饰：青绿的删不掉（应取消订阅），
 * 灰色的能删。提前预告，省得用户点了删除才发现不行。
 */

import './SourceBadge.css';

export function SourceBadge({ origin, name }: { origin: string; name?: string }) {
  const official = origin === 'official';
  return (
    <span className={`sbadge sbadge--${official ? 'official' : 'user'}`}>
      {name ?? (official ? 'logo!' : '自导入')}
    </span>
  );
}
