import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // 容器内挂卷时 inotify 常失效，退回轮询
    watch: { usePolling: true },
  },
});
