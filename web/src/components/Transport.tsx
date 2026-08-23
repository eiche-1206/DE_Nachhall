/* 控制条。随**步骤**变化，不是随状态微调。
 *
 * **容器高度恒定 68px**，按钮增减不引起布局位移（设计原则 3）。
 * 高度写在 --h-transport 上，按钮列表怎么变都不碰它。
 *
 * 每一步的主按钮都绑 Space，含义永远是「重复当前这一步」，但**文案随步骤
 * 走，不用统一措辞** —— 都叫「再来一遍」看似整齐，第 ⑤ 步却读不出
 * 「再放我的」的意思，正是这个含糊让人以为还需要一个额外按钮。
 */

import type { ButtonVariant } from './Button';
import { Button } from './Button';
import './Transport.css';

export interface TransportAction {
  key: string;
  label: string;
  kbd?: string;
  kbdSide?: 'start' | 'end';
  variant?: ButtonVariant;
  onClick: () => void;
  disabled?: boolean;
}

export function Transport({ actions }: { actions: TransportAction[] }) {
  return (
    <div className="transport">
      {actions.map((a) => (
        <Button
          key={a.key}
          variant={a.variant ?? 'secondary'}
          kbd={a.kbd}
          kbdSide={a.kbdSide}
          onClick={a.onClick}
          disabled={a.disabled}
        >
          {a.label}
        </Button>
      ))}
    </div>
  );
}
