// 展示端源码已按职责分片到 web-src/parts/；测试按构建顺序拼合后再切片，
// 保证「切片锚点」与真实产物一致，且不再依赖单个 124KB 文件。
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const PARTS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../web-src/parts');

export const partNames = fs.readdirSync(PARTS)
  .filter((f) => f.endsWith('.js')).sort();

export const displaySource = partNames
  .map((f) => fs.readFileSync(path.join(PARTS, f), 'utf8'))
  .join('\n');
