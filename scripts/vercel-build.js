const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const outDir = path.join(root, 'public');
const entries = ['index.html', 'data', 'v2', path.join('scripts', 'xlsx.full.min.js')];

function copyEntry(relativePath) {
  const source = path.join(root, relativePath);
  const target = path.join(outDir, relativePath);
  const stats = fs.statSync(source);

  if (stats.isDirectory()) {
    fs.cpSync(source, target, { recursive: true });
    return;
  }

  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.copyFileSync(source, target);
}

fs.rmSync(outDir, { recursive: true, force: true });
fs.mkdirSync(outDir, { recursive: true });

for (const entry of entries) {
  copyEntry(entry);
}

console.log(`Built static site into ${path.relative(root, outDir)}/`);
