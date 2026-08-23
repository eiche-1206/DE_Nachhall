/* 后端调用的唯一入口。
 *
 * 两条规矩：
 *   1. API 类型**全部**来自 api.types.ts（openapi-typescript 生成）。
 *      手写一份等于给自己留一个和后端悄悄漂移的机会。改了后端跑 npm run gen:api。
 *   2. 错误统一成 ApiError。后端所有路由返回 { error: { code, message } }，
 *      message 面向用户且说明了怎么修，所以 UI 直接展示它，不要自己编文案。
 */

import type { components } from './api.types';

type S = components['schemas'];

export type MediaListItem = S['MediaListItem'];
export type MediaDetail = S['MediaDetail'];
export type ChunkOut = S['ChunkOut'];
export type ChapterOut = S['ChapterOut'];
export type JobStatus = S['JobStatus'];
export type ImportResponse = S['ImportResponse'];
export type SourceOut = S['SourceOut'];

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

/** 网络层挂了（服务没起、断网）也走 ApiError，UI 只需处理一种异常。 */
const OFFLINE = new ApiError(0, 'NETWORK', '连不上服务，确认后端已经启动。');

type ErrorBody = { error?: { code?: string; message?: string } };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: init?.body ? { 'Content-Type': 'application/json', ...init?.headers } : init?.headers,
    });
  } catch {
    throw OFFLINE;
  }

  if (res.status === 204) return undefined as T;

  if (!res.ok) {
    let body: ErrorBody = {};
    try {
      body = (await res.json()) as ErrorBody;
    } catch {
      /* 后端理论上总返回 JSON，但代理或超时可能塞别的东西进来 */
    }
    throw new ApiError(
      res.status,
      body.error?.code ?? 'HTTP_ERROR',
      body.error?.message ?? `请求失败（${res.status}）。`
    );
  }

  return (await res.json()) as T;
}

export const api = {
  health: () => request<{ status: string }>('/api/health'),

  timeline: (status?: string[]) => {
    const q = status?.length ? `?${status.map((s) => `status=${encodeURIComponent(s)}`).join('&')}` : '';
    return request<{ items: MediaListItem[] }>(`/api/media${q}`);
  },

  media: (id: number) => request<MediaDetail>(`/api/media/${id}`),

  chunks: (id: number) =>
    request<{ media_id: number; chunks: ChunkOut[] }>(`/api/media/${id}/chunks`),

  /** probe 同步执行，这一条会慢 1–3 秒，调用方要给出等待反馈。 */
  importUrl: (url: string) =>
    request<ImportResponse>('/api/media', { method: 'POST', body: JSON.stringify({ url }) }),

  retry: (id: number) => request<MediaListItem>(`/api/media/${id}/retry`, { method: 'POST' }),

  remove: (id: number) => request<void>(`/api/media/${id}`, { method: 'DELETE' }),

  sources: () => request<{ items: SourceOut[] }>('/api/sources'),
};

/** 视频与封面走 <video src> / <img src>，不经 fetch —— Range 要交给浏览器自己发。 */
export const mediaUrl = {
  stream: (id: number) => `${API_BASE}/api/media/${id}/stream`,
  thumb: (id: number) => `${API_BASE}/api/media/${id}/thumb`,
};
