import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { resolve } from 'node:path';

// 工作台走独立构建链，主渲染页（web/index.html，111KB 原生 ES modules）不进此处，
// 保持「核心零 npm 依赖、离线可跑」。产物落到仓库根的 web/studio-dist，
// 由 Python 服务以 /studio/ 前缀托管，与主服务同源，/__api/* 鉴权天然通过。
export default defineConfig({
  root: __dirname,
  base: '/studio/',
  plugins: [vue()],
  build: {
    outDir: resolve(__dirname, '../web/studio-dist'),
    emptyOutDir: true,
    assetsDir: 'assets',
  },
  server: {
    proxy: {
      '/__api': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
      },
    },
  },
});
