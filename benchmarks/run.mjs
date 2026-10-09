// Benchmark du moteur JS (constats C3/C4). Prérequis : `npm run build` dans js-engine/.
//   node benchmarks/run.mjs <dossier_catalogues> 100 200 400 ...
import { readFileSync } from "node:fs";
import { performance } from "node:perf_hooks";
import { join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import os from "node:os";

const here = dirname(fileURLToPath(import.meta.url));
const { SearchEngine, CompressedPostingsList } = await import(pathToFileURL(join(here, "../js-engine/dist/index.js")).href);
const dir = process.argv[2];
const sizes = process.argv.slice(3).map(Number);

function pct(sorted, p) { return sorted[Math.max(0, Math.floor(sorted.length * p) - 1)]; }
function lat(eng, vocab, fuzzy, n = 300) {
  let seed = 11; const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
  const xs = [];
  for (let i = 0; i < n; i++) {
    const w = vocab[Math.floor(rnd() * vocab.length)];
    const q = w.slice(0, 2 + Math.floor(rnd() * 4));
    eng.clearCache();
    const t0 = performance.now(); eng.search(q, {}, fuzzy, 1); xs.push(performance.now() - t0);
  }
  xs.sort((a, b) => a - b);
  return [xs[Math.floor(xs.length / 2)], pct(xs, 0.99)];
}

console.log(`Machine: ${os.platform()} ${os.release()} | Node ${process.version}`);
console.log("| Produits | Indexation (ms) | Rapport | Recherche p50/p99 (ms) | Floue p50/p99 (ms) |");
console.log("|---:|---:|---:|---:|---:|");
let prev = null;
for (const n of sizes) {
  const cat = JSON.parse(readFileSync(join(dir, `catalog_${n}.json`), "utf-8"));
  const eng = new SearchEngine(1);
  const t0 = performance.now(); eng.loadCatalog({ products: cat.products }); const t = performance.now() - t0;
  const [s50, s99] = lat(eng, cat.vocab, false), [f50, f99] = lat(eng, cat.vocab, true);
  console.log(`| ${n} | ${t.toFixed(1)} | ${prev ? (t / prev).toFixed(2) : "—"} | ${s50.toFixed(3)} / ${s99.toFixed(3)} | ${f50.toFixed(3)} / ${f99.toFixed(3)} |`);
  prev = t;
}

// Postings : 500 identifiants aléatoires, Set natif vs delta+VarInt
if (global.gc) {
  let seed = 3; const ids = new Set(); while (ids.size < 500) { seed = (seed * 1103515245 + 12345) & 0x7fffffff; ids.add(1 + (seed % 100000)); }
  global.gc(); const a = process.memoryUsage().heapUsed;
  const sets = Array.from({ length: 200 }, () => new Set(ids)); global.gc();
  const setBytes = (process.memoryUsage().heapUsed - a) / 200;
  const pl = new CompressedPostingsList(); for (const i of ids) pl.add(i); pl.flush();
  console.log(`\nPostings (500 ids) : Set ≈ ${Math.round(setBytes)} octets, delta+VarInt = ${pl.memoryBytes()} octets`
    + ` (-${(100 * (1 - pl.memoryBytes() / setBytes)).toFixed(1)} %) ; ${sets.length} Set instanciés`);
}
