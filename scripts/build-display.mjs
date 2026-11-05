// 展示端构建第一步：把按职责分片的源码拼成单一模块入口。
// 分片之间共享一个模块作用域（渲染引擎是命令式的 Three.js 循环，强行拆成
// 互不共享的 ES 模块会引入大量隐式状态传递，收益不抵风险）；分片本身已按
// 运行时 / 场景 / 打印引擎 / 交互层分开，纯逻辑另放在 core/ 下作为真模块。
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SRC = path.join(ROOT, 'web-src');
const partsDir = path.join(SRC, 'parts');
const names = fs.readdirSync(partsDir).filter((f) => f.endsWith('.js')).sort();
if (!names.length) throw new Error('web-src/parts/ 下没有源码分片');

const imports = fs.readFileSync(path.join(SRC, 'imports.txt'), 'utf8');
const header = [
  '// 自动生成，请勿直接编辑：源文件在 web-src/parts/ 与 web-src/styles/。',
  '// 重新生成：bash scripts/build-display.sh',
  '',
].join('\n');
const body = names.map((n) =>
  `\n// ── ${n} ──\n` + fs.readFileSync(path.join(partsDir, n), 'utf8').trimEnd()
).join('\n');

fs.writeFileSync(path.join(SRC, 'app.entry.js'), header + imports + body + '\n', 'utf8');
console.log(`✓ 已拼合 ${names.length} 个源码分片 → web-src/app.entry.js`);
