// 不 import vite：构建器由 studio/node_modules 提供，配置文件本身保持零依赖，
// 这样在根 package.json 未安装依赖时也能直接构建。
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// 展示端构建链：源码 web-src/ → 产物 web/app/（入库，clone 后无需 npm 即可运行）。
// Vite 只在构建期使用，运行时仍是原生 ES module，three.js 继续 vendored。
// 控制台走另一条独立配置：studio/vite.config.js → web/studio-dist/。
const ROOT = path.dirname(fileURLToPath(import.meta.url));

export default {
  root: ROOT,
  publicDir: false,
  logLevel: 'warn',
  // vendored 的 OrbitControls / Reflector 用裸模块名 three，构建期指回本地文件。
  resolve: {
    alias: { three: path.join(ROOT, 'assets', 'three.module.js') },
  },
  build: {
    outDir: path.join(ROOT, 'web', 'app'),
    emptyOutDir: true,
    target: 'es2022',
    minify: false,
    cssCodeSplit: false,
    rollupOptions: {
      input: path.join(ROOT, 'web-src', 'app.entry.js'),
      output: {
        entryFileNames: 'app.js',
        assetFileNames: 'app.[ext]',
      },
    },
  },
};
