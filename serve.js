// Local preview server. Usage: node serve.js [port] [--vendor <dir>]
// Serves web/index.html wrapped into a full document (same wrapper as build_site.js).
// With --vendor, the two CDN scripts are served from <dir> (maplibre-gl.js, deck.min.js) for offline use.
const http = require('http');
const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const port = parseInt(args.find(a => /^\d+$/.test(a)) || '8080', 10);
const vi = args.indexOf('--vendor');
const vendor = vi >= 0 ? path.resolve(args[vi + 1]) : null;
const web = path.join(__dirname, 'web');
const types = { '.json': 'application/json', '.js': 'text/javascript', '.html': 'text/html; charset=utf-8', '.css': 'text/css' };

const { wrap } = require('./build_site.js');

http.createServer((req, res) => {
  const url = decodeURIComponent(req.url.split('?')[0]);
  if (url === '/' || url === '/index.html') {
    let page = fs.readFileSync(path.join(web, 'index.html'), 'utf8');
    if (vendor) {
      page = page.replace(/https:\/\/unpkg\.com\/maplibre-gl@[\d.]+\/dist\/maplibre-gl\.js/, '/vendor/maplibre-gl.js')
                 .replace(/https:\/\/unpkg\.com\/deck\.gl@[\d.]+\/dist\.min\.js/, '/vendor/deck.min.js');
    }
    res.writeHead(200, { 'content-type': types['.html'] });
    return res.end(wrap(page));
  }
  const base = url.startsWith('/vendor/') && vendor ? vendor : web;
  const file = path.normalize(path.join(base, url.replace(/^\/vendor\//, '/')));
  if (!file.startsWith(base) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); return res.end('not found'); }
  res.writeHead(200, { 'content-type': types[path.extname(file)] || 'application/octet-stream' });
  fs.createReadStream(file).pipe(res);
}).listen(port, () => console.log('http://localhost:' + port));
