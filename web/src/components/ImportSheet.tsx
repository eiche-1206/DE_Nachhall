/* 导入浮层。
 *
 * 提交是**同步 probe，1–3 秒**。期间输入框禁用、按钮转圈、显示「正在读取
 * 视频信息…」。成功时直接回显标题与时长 —— 这是 probe 顺带拿到的，
 * 比一句「链接可用」有信息量得多，也让人在导入前就确认贴对了。
 *
 * **四种失败必须分开说。** 下架 / 地域限制 / 需登录 / 站点不支持，用户的
 * 下一步动作完全不同（换个视频 / 挂代理 / 放弃 / 换站点）。文案由后端给，
 * 前端不自己编 —— 后端的 message 已经写清了怎么修。
 */

import { useState } from 'react';

import { ApiError, api } from '../lib/api';
import { duration } from '../lib/format';
import { Button } from './Button';
import { Popover } from './Popover';
import './ImportSheet.css';

type Feedback =
  | { kind: 'idle' }
  | { kind: 'probing' }
  | { kind: 'ok'; text: string }
  | { kind: 'err'; text: string };

const HINT = '粘贴视频链接。YouTube、ZDF、ARD 等站点都支持。';

export function ImportSheet({
  open,
  onClose,
  onImported,
}: {
  open: boolean;
  onClose: () => void;
  onImported: (mediaId: number, alreadyExists: boolean) => void;
}) {
  const [url, setUrl] = useState('');
  const [fb, setFb] = useState<Feedback>({ kind: 'idle' });
  const busy = fb.kind === 'probing';

  async function submit() {
    if (!url.trim() || busy) return;
    setFb({ kind: 'probing' });
    try {
      const r = await api.importUrl(url.trim());
      if (r.already_exists) {
        setFb({ kind: 'ok', text: '这一期已经在库里了 —— 直接打开，不会重复转写。' });
      } else {
        setFb({ kind: 'ok', text: `${r.title} · ${duration(r.duration_ms)} —— 已加入队列。` });
      }
      setUrl('');
      onImported(r.media_id, r.already_exists);
    } catch (e) {
      // 后端的 message 已经说明了怎么修，原样展示，不要在这里重写文案
      setFb({ kind: 'err', text: e instanceof ApiError ? e.message : '导入失败，请重试。' });
    }
  }

  return (
    <Popover open={open} onClose={onClose} title="导入素材" width={392}>
      <div className="isheet">
        <div className="isheet__row">
          <input
            className="isheet__input"
            value={url}
            disabled={busy}
            onChange={(e) => {
              setUrl(e.target.value);
              if (fb.kind !== 'idle') setFb({ kind: 'idle' });
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void submit();
            }}
            placeholder="粘贴视频链接…"
            aria-label="视频链接"
          />
          <Button variant="primary" onClick={() => void submit()} disabled={busy || !url.trim()}>
            {busy ? '读取中' : '导入'}
          </Button>
        </div>
        <p className={`isheet__fb isheet__fb--${fb.kind}`}>
          {fb.kind === 'idle' ? HINT : null}
          {fb.kind === 'probing' ? '◌ 正在读取视频信息…' : null}
          {fb.kind === 'ok' || fb.kind === 'err' ? fb.text : null}
        </p>
      </div>
    </Popover>
  );
}
