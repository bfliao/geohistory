// Build the static site (for GitHub Pages or any static host).
// Usage: node build_site.js [outDir]   (default: _site)
// web/index.html is a page fragment (no <html>/<head>); this wraps it into a full document and copies web/data.
const fs = require('fs');
const path = require('path');

const web = path.join(__dirname, 'web');
const HEAD = `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="地图加时间轴的世界历史事件浏览器：点击任意地点，查看该地周边各时期的事件、聚居地、迁徙路线和疆域。">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Ccircle cx='8' cy='8' r='7' fill='%230e5f70'/%3E%3Ccircle cx='8' cy='8' r='2.5' fill='%23f6f8f6'/%3E%3C/svg%3E">
<style>:root{color-scheme:light;padding:env(safe-area-inset-top,0px) 0 env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>
`;

// The fragment starts with <meta>/<title>/<link>/<style>, which the HTML parser keeps in <head>;
// <body> opens implicitly at the first content element.
function wrap(fragment) {
  return HEAD + fragment + '\n</body>\n</html>\n';
}

function build(outDir) {
  fs.rmSync(outDir, { recursive: true, force: true });
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, 'index.html'), wrap(fs.readFileSync(path.join(web, 'index.html'), 'utf8')));
  fs.cpSync(path.join(web, 'data'), path.join(outDir, 'data'), { recursive: true });
  fs.writeFileSync(path.join(outDir, '.nojekyll'), '');
  let n = 0, bytes = 0;
  (function walk(d) { for (const f of fs.readdirSync(d, { withFileTypes: true })) { const p = path.join(d, f.name); if (f.isDirectory()) walk(p); else { n++; bytes += fs.statSync(p).size; } } })(outDir);
  console.log(`built ${outDir}: ${n} files, ${(bytes / 1048576).toFixed(1)} MB`);
}

module.exports = { wrap };
if (require.main === module) build(path.resolve(process.argv[2] || '_site'));
