/* 路由参数的解析。集中在这里，页面不各自 parseInt。 */

/** 路径里的 :id。非法值返回 null，页面据此显示「找不到」而不是崩。 */
export function parseMediaId(raw: string | undefined): number | null {
  if (!raw) return null;
  const n = Number(raw);
  return Number.isInteger(n) && n > 0 ? n : null;
}

/** ?chunk=N。缺省或非法一律从第 0 段开始 —— 直达链接坏掉不该挡住跟读。 */
export function parseChunkIndex(search: string): number {
  const raw = new URLSearchParams(search).get('chunk');
  if (raw === null) return 0;
  const n = Number(raw);
  return Number.isInteger(n) && n >= 0 ? n : 0;
}
