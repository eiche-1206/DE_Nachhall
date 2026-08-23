/* 听写对照。
 *
 * **不做 diff、不判对错**（PRD Out of Scope 第二条）。上下叠，靠同宽对齐
 * 让差异自己浮现：两块同宽、同 --t-german、同行高、同内边距，相同的词
 * 自动垂直对齐，写错或漏掉的地方**从那里开始错位** —— 错位本身就是信号，
 * 但它是排版的自然结果，不是标记。
 *
 * 明令禁止：不得加入任何形式的差异标记（高亮、删除线、颜色、相似度分数）。
 * 实现时看到两块文本并排，加个 diff 高亮只是三行代码且看起来像改进，
 * 正因如此这条必须写死。
 *
 * 为什么上下叠而不是左右并排：960px 一分为二每栏只剩 ~450px，22 词的德语
 * 段落要折 3–4 行，而且两边行数不同（写的短、原文长），左右根本对不齐。
 */

import './ComparePanel.css';

export function ComparePanel({ mine, original }: { mine: string; original: string }) {
  return (
    <div className="cmp">
      <div className="cmp__block">
        <span className="label">我写的</span>
        {/* 两块的 className 只差底色，字号行高内边距全部来自 .cmp__text */}
        <div className="cmp__text cmp__text--mine german">{mine || '（没写）'}</div>
      </div>
      <div className="cmp__block">
        <span className="label">原文</span>
        <div className="cmp__text cmp__text--orig german">{original}</div>
      </div>
    </div>
  );
}
