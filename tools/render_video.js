#!/usr/bin/env node
// 以 Playwright 逐格擷取 index.html?render=1，再用 ffmpeg 合成 MP4（含旁白音軌）
// 用法：
//   node tools/render_video.js snap [outdir]      每頁結尾截圖（檢查版面）
//   node tools/render_video.js video [fps] [workers]
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'playwright');
const { spawn, execFileSync } = require('child_process');
const fs = require('fs'), path = require('path');
const ROOT = path.resolve(__dirname, '..');
const URL = 'file://' + path.join(ROOT, 'index.html') + '?render=1';
const WORK = path.join(ROOT, 'tools', '.work');

async function openPage(browser) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
  await page.goto(URL, { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(500);
  return page;
}

async function snap(outdir) {
  fs.mkdirSync(outdir, { recursive: true });
  const browser = await chromium.launch();
  const page = await openPage(browser);
  const marks = await page.evaluate(() => window.MANIFEST.slides.map(s => [s.id, s.start, s.dur]));
  for (const [id, start, dur] of marks) {
    await page.evaluate(t => window.__seek(t), start + dur - 0.3);
    await page.screenshot({ path: path.join(outdir, `${id}.png`) });
  }
  await browser.close();
}

async function segment(browser, fps, f0, f1, file) {
  const page = await openPage(browser);
  const ff = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-',
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '23', '-pix_fmt', 'yuv420p', '-r', String(fps), file], { stdio: ['pipe', 'inherit', 'inherit'] });
  for (let f = f0; f < f1; f++) {
    await page.evaluate(t => window.__seek(t), f / fps);
    const buf = await page.screenshot({ type: 'jpeg', quality: 90 });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if ((f - f0) % 300 === 0) console.log(`  ${path.basename(file)} ${f - f0}/${f1 - f0}`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  await page.close();
}

async function video(fps, workers) {
  fs.mkdirSync(WORK, { recursive: true });
  const browser = await chromium.launch();
  const p0 = await openPage(browser);
  const total = await p0.evaluate(() => window.__total); await p0.close();
  const frames = Math.ceil(total * fps), per = Math.ceil(frames / workers), parts = [];
  console.log(`total ${total.toFixed(1)}s, ${frames} frames @${fps}fps, ${workers} workers`);
  const jobs = [];
  for (let w = 0; w < workers; w++) {
    const f0 = w * per, f1 = Math.min(frames, f0 + per); if (f0 >= f1) break;
    const file = path.join(WORK, `part${w}.mp4`); parts.push(file);
    jobs.push(segment(browser, fps, f0, f1, file));
  }
  await Promise.all(jobs);
  await browser.close();
  const list = path.join(WORK, 'parts.txt');
  fs.writeFileSync(list, parts.map(p => `file '${p}'`).join('\n'));
  const out = path.join(ROOT, 'video', 'TVM_威脅與弱點管理.mp4');
  fs.mkdirSync(path.dirname(out), { recursive: true });
  execFileSync('ffmpeg', ['-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', list, '-i', path.join(WORK, 'narration.wav'),
    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '96k', '-shortest', '-movflags', '+faststart', out], { stdio: 'inherit' });
  execFileSync('python3', [path.join(__dirname, 'add_chapters.py'), out], { stdio: 'inherit' });
  console.log('->', out);
}

const [mode = 'snap', a, b] = process.argv.slice(2);
(mode === 'video' ? video(+a || 20, +b || 4) : snap(a || path.join(WORK, 'snap'))).catch(e => { console.error(e); process.exit(1); });
