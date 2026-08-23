/* 设置浮层。**两组，全平铺，无嵌套**：
 *   回声环节 —— 三项，决定运行时有哪几步
 *   显示     —— 一项，只管画面上摆什么，不影响任何步骤
 * 分组不是嵌套：两组都在同一层，没有折叠、没有子选项。混在一起才是问题 ——
 * 「段落进度条」和「听写」放同一串里，会让人以为关掉它也会少一个环节。
 *
 * 三条硬规则：
 *   1. **不出现假开关。** ① 显示静态标签「始终」，没有可点击控件 ——
 *      它是闭环的地基，关不掉；既然关不掉就别给开关，
 *      给一个能点但点了没意义的控件比不给更糟。
 *   2. **不出现派生只读项。** 二次播放与回放都不单列，它们跟着录音走，
 *      并进「③ 录音与回放」：二次播放是录音前的准备，回放是录音后的对比，
 *      两者都没有独立存在的理由。设置里 3 项、运行时最多 6 步，
 *      这是有意的非一一对应。
 *   3. **不做嵌套子选项。** 「提交后自动展示答案」「录音前自动重听一遍」
 *      都写死为自动，不给开关。
 *
 * 切换即时生效，**无保存按钮、无 Toast** —— 生效本身就是反馈。
 */

import { useSettings } from '../settings/SettingsProvider';
import type { SettingsKey } from '../settings/types';
import { Popover } from './Popover';
import './SettingsPanel.css';

interface Row {
  no: string;
  title: string;
  note: string;
  /** 无 key = 静态标签，不给控件 */
  key?: SettingsKey;
  fixedLabel?: string;
}

const DISPLAY_ROWS: Row[] = [
  {
    no: '—',
    title: '段落进度条',
    note: '视频下方，点哪格跳哪段',
    key: 'segmentBar',
  },
];

const ROWS: Row[] = [
  {
    no: '00',
    title: '全文播放',
    note: '① 播完自动进下一段，一路连到全文结束，不进听写与录音',
    key: 'continuousPlay',
  },
  { no: '01', title: '播放原声', note: '到段尾自动暂停', fixedLabel: '始终' },
  { no: '02', title: '听写', note: '写完提交，就地展示答案', key: 'dictation' },
  {
    no: '03',
    title: '录音与回放',
    note: '录音前自动重听一遍并展示原文；录完立即回放对比',
    key: 'record',
  },
];

function Switch({
  label,
  on,
  onToggle,
}: {
  label: string;
  on: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      className={`sw${on ? ' sw--on' : ''}`}
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={onToggle}
    >
      <span className="sw__knob" />
    </button>
  );
}

export function SettingsPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { settings, toggle } = useSettings();

  return (
    <Popover open={open} onClose={onClose} title="回声环节" width={288}>
      <ul className="sset">
        {ROWS.map((r) => (
          <li key={r.no} className="sset__row">
            <span className="sset__no tnum">{r.no}</span>
            <span className="sset__body">
              <span className="sset__title">{r.title}</span>
              <span className="sset__note">{r.note}</span>
            </span>
            {r.key ? (
              <Switch label={r.title} on={settings[r.key]} onToggle={() => toggle(r.key!)} />
            ) : (
              <span className="sset__fixed">{r.fixedLabel}</span>
            )}
          </li>
        ))}
      </ul>

      <div className="sset__group">显示</div>
      <ul className="sset">
        {DISPLAY_ROWS.map((r) => (
          <li key={r.title} className="sset__row">
            <span className="sset__no tnum">{r.no}</span>
            <span className="sset__body">
              <span className="sset__title">{r.title}</span>
              <span className="sset__note">{r.note}</span>
            </span>
            <Switch
              label={r.title}
              on={settings[r.key as SettingsKey]}
              onToggle={() => toggle(r.key as SettingsKey)}
            />
          </li>
        ))}
      </ul>

      <footer className="sset__foot">
        全局设置，改一次以后每期都是这样。存在浏览器本地。
        <br />
        听写提交后自动展示答案，不需要再点一次。
        <br />
        二次播放与回放都跟着录音走，不单列。
      </footer>
    </Popover>
  );
}
