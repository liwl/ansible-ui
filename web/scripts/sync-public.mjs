// 构建产物同步到 Flask 静态目录 public/（跨平台，node 执行）
import { cpSync, existsSync, readdirSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const dist = resolve(here, '..', 'dist');
const publicDir = resolve(here, '..', '..', 'public');

if (!existsSync(dist)) {
  console.error('未找到 dist 目录，请先执行 vite build');
  process.exit(1);
}

const distAssets = join(dist, 'assets');
const publicAssets = join(publicDir, 'assets');

if (existsSync(distAssets)) {
  rmSync(publicAssets, { recursive: true, force: true });
  cpSync(distAssets, publicAssets, { recursive: true });
  console.log(`已同步 assets: ${readdirSync(publicAssets).length} 个文件`);
}

cpSync(join(dist, 'index.html'), join(publicDir, 'index.html'));
console.log('已同步 index.html');
