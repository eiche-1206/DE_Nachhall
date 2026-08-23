/* 路由骨架。
 *
 * 只有三个页面级视图。听写、设置、导入都**不是页面** —— 它们是当前页面
 * 里的一个态或一层浮层。做成路由会让「回到刚才那一段」变成前进后退问题。
 *
 *   /                      首页时间线
 *   /episode/:id           详情页
 *   /episode/:id/echo      回声闭环，?chunk=N 直达某段
 */

import { Navigate, Route, Routes } from 'react-router-dom';

import { DetailPage } from './routes/DetailPage';
import { EchoPage } from './routes/EchoPage';
import { HomePage } from './routes/HomePage';

export function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/episode/:id" element={<DetailPage />} />
      <Route path="/episode/:id/echo" element={<EchoPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
