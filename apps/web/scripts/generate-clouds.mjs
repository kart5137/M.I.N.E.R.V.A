// Generates public/textures/clouds.png: the decorative cloud layer of the globes.
//
//   node scripts/generate-clouds.mjs            (writes the PNG; needs no browser)
//
// Our own procedural texture (no third-party imagery): 3D simplex noise sampled on a
// cylinder so the image wraps seamlessly at 180°, domain-warped fractal noise for swirled,
// wind-stretched shapes, more cloud in the tropics and mid-latitude storm belts, none near
// the poles. Rows are laid out in Web Mercator (±85.05°), the projection of MapLibre image
// sources, so clouds are not stretched towards the poles. White with alpha; decoration only.

import { writeFileSync, mkdirSync } from "node:fs";
import { deflateSync } from "node:zlib";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const W = 1024;
const H = 1024; // Mercator square
const SEED = 20261111;
const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "textures", "clouds.png");

// --- 3D simplex noise (after Stefan Gustavson's public-domain reference) -------------------
const grad3 = [[1,1,0],[-1,1,0],[1,-1,0],[-1,-1,0],[1,0,1],[-1,0,1],[1,0,-1],[-1,0,-1],[0,1,1],[0,-1,1],[0,1,-1],[0,-1,-1]];
const perm = new Uint8Array(512);
{
  const p = new Uint8Array(256).map((_, i) => i);
  let s = SEED >>> 0;
  for (let i = 255; i > 0; i--) {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    const j = s % (i + 1);
    [p[i], p[j]] = [p[j], p[i]];
  }
  for (let i = 0; i < 512; i++) perm[i] = p[i & 255];
}
const F3 = 1 / 3;
const G3 = 1 / 6;
function simplex3(x, y, z) {
  const s = (x + y + z) * F3;
  const i = Math.floor(x + s), j = Math.floor(y + s), k = Math.floor(z + s);
  const t = (i + j + k) * G3;
  const x0 = x - (i - t), y0 = y - (j - t), z0 = z - (k - t);
  let i1, j1, k1, i2, j2, k2;
  if (x0 >= y0) {
    if (y0 >= z0) { i1 = 1; j1 = 0; k1 = 0; i2 = 1; j2 = 1; k2 = 0; }
    else if (x0 >= z0) { i1 = 1; j1 = 0; k1 = 0; i2 = 1; j2 = 0; k2 = 1; }
    else { i1 = 0; j1 = 0; k1 = 1; i2 = 1; j2 = 0; k2 = 1; }
  } else if (y0 < z0) { i1 = 0; j1 = 0; k1 = 1; i2 = 0; j2 = 1; k2 = 1; }
  else if (x0 < z0) { i1 = 0; j1 = 1; k1 = 0; i2 = 0; j2 = 1; k2 = 1; }
  else { i1 = 0; j1 = 1; k1 = 0; i2 = 1; j2 = 1; k2 = 0; }
  const x1 = x0 - i1 + G3, y1 = y0 - j1 + G3, z1 = z0 - k1 + G3;
  const x2 = x0 - i2 + 2 * G3, y2 = y0 - j2 + 2 * G3, z2 = z0 - k2 + 2 * G3;
  const x3 = x0 - 1 + 0.5, y3 = y0 - 1 + 0.5, z3 = z0 - 1 + 0.5;
  const ii = i & 255, jj = j & 255, kk = k & 255;
  const corner = (gx, cx, cy, cz) => {
    let tt = 0.6 - cx * cx - cy * cy - cz * cz;
    if (tt < 0) return 0;
    const g = grad3[gx % 12];
    tt *= tt;
    return tt * tt * (g[0] * cx + g[1] * cy + g[2] * cz);
  };
  const n0 = corner(perm[ii + perm[jj + perm[kk]]], x0, y0, z0);
  const n1 = corner(perm[ii + i1 + perm[jj + j1 + perm[kk + k1]]], x1, y1, z1);
  const n2 = corner(perm[ii + i2 + perm[jj + j2 + perm[kk + k2]]], x2, y2, z2);
  const n3 = corner(perm[ii + 1 + perm[jj + 1 + perm[kk + 1]]], x3, y3, z3);
  return 32 * (n0 + n1 + n2 + n3); // ≈ [-1, 1]
}

/** Fractal noise on a point of the unit-radius cylinder (angle a, height h). */
function fbm(a, h, freq, octaves, offset) {
  let sum = 0, amp = 0.5, norm = 0, f = freq;
  for (let o = 0; o < octaves; o++) {
    sum += amp * simplex3(Math.cos(a) * f + offset, Math.sin(a) * f + offset * 0.7, h * f + o * 3.1);
    norm += amp;
    amp *= 0.5;
    f *= 2.03;
  }
  return sum / norm; // ≈ [-1, 1]
}

function band(lat) {
  const l = Math.abs(lat);
  const g = (m, s) => Math.exp(-((l - m) ** 2) / (2 * s * s));
  const polar = 1 - Math.min(Math.max((l - 60) / 12, 0), 1);
  return (0.5 + 0.22 * g(6, 8) + 0.28 * g(52, 11) - 0.2 * g(25, 7)) * polar;
}

// --- render ------------------------------------------------------------------------------
const ga = new Uint8Array(W * H * 2); // grey + alpha
const maxY = Math.log(Math.tan(Math.PI / 4 + (85.05 * Math.PI) / 360));
for (let y = 0; y < H; y++) {
  const my = maxY * (1 - (2 * (y + 0.5)) / H); // Mercator y, top = north
  const lat = (2 * Math.atan(Math.exp(my)) - Math.PI / 2) * (180 / Math.PI);
  const b = band(lat);
  if (b <= 0.005) continue;
  const h = lat / 57.3; // radians of latitude: isotropic with the cylinder's angle
  for (let x = 0; x < W; x++) {
    const a = (2 * Math.PI * (x + 0.5)) / W;
    // Domain warp, stronger east–west (winds stretch clouds into streaks).
    const wa = a + 0.16 * fbm(a, h, 1.4, 3, 11.3);
    const wh = h + 0.05 * fbm(a, h, 1.4, 3, 47.9);
    const n = fbm(wa, wh * 1.6, 2.6, 6, 0); // ≈ [-1, 1]; squashed north–south
    const v = (n * 0.5 + 0.5) * (0.55 + b);
    const t = Math.min(Math.max((v - 0.6) / 0.32, 0), 1);
    // Wispy interior: fine noise thins the cloud body.
    const fine = 0.55 + 0.45 * (fbm(a, h, 14, 3, 91.7) * 0.5 + 0.5);
    const alpha = t * t * (3 - 2 * t) * fine;
    if (alpha <= 0.01) continue;
    const i = (y * W + x) * 2;
    ga[i] = 250;
    ga[i + 1] = Math.round(Math.min(alpha, 1) * 255);
  }
}

// --- PNG encode (grey + alpha, no filter) ----------------------------------------------------------
const crcTable = new Int32Array(256).map((_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c;
});
function crc32(buf) {
  let c = -1;
  for (const b of buf) c = crcTable[(c ^ b) & 255] ^ (c >>> 8);
  return (c ^ -1) >>> 0;
}
function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
}
for (let i = 0; i < ga.length; i += 2) if (ga[i + 1] === 0) ga[i] = 250; // uniform grey compresses
const raw = Buffer.alloc((W * 2 + 1) * H);
for (let y = 0; y < H; y++) {
  raw[y * (W * 2 + 1)] = 0;
  Buffer.from(ga.buffer, y * W * 2, W * 2).copy(raw, y * (W * 2 + 1) + 1);
}
const ihdr = Buffer.alloc(13);
ihdr.writeUInt32BE(W, 0); ihdr.writeUInt32BE(H, 4);
ihdr[8] = 8; ihdr[9] = 4; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
const png = Buffer.concat([
  Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
  chunk("IHDR", ihdr),
  chunk("IDAT", deflateSync(raw, { level: 9 })),
  chunk("IEND", Buffer.alloc(0)),
]);
mkdirSync(dirname(OUT), { recursive: true });
writeFileSync(OUT, png);
console.log(`wrote ${OUT} (${(png.length / 1024).toFixed(0)} KB)`);
