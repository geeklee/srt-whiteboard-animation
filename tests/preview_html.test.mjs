// 预览台（assets/preview.html）里纯逻辑部分的测试。
// 做法：抽出 <script> 原文，在最小 DOM 桩里跑一遍，再取出内部函数做断言。
// 这样测的是仓库里真实的那段代码，而不是测试里复制的一份。
//
// 运行： node tests/preview_html.test.mjs
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(join(here, '..', 'assets', 'preview.html'), 'utf8');

const match = html.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(match, 'preview.html 里应有一段 <script>');
const source = match[1];

// ---------- 最小 DOM 桩 ----------
function stubEl() {
  const store = {
    classList: { add() {}, remove() {} }, dataset: {}, style: {}, files: [],
    value: '', textContent: '', innerHTML: '', disabled: false, hidden: false,
    complete: false, naturalWidth: 0, naturalHeight: 0,
  };
  return new Proxy(store, {
    get(target, prop) {
      if (prop in target) return target[prop];
      return () => stubEl();          // 任意方法调用都返回一个新桩
    },
    set(target, prop, value) { target[prop] = value; return true; },
  });
}

const downloads = [];
const context = {
  document: {
    getElementById: () => stubEl(),
    createElement: () => stubEl(),
    body: { appendChild() {} },
    addEventListener() {},
  },
  window: { addEventListener() {} },
  Image: class { set src(_v) {} get complete() { return false; } },
  performance: { now: () => 0 },
  requestAnimationFrame() {},
  URL: { createObjectURL: () => 'blob:stub', revokeObjectURL() {} },
  Blob: class { constructor(parts) { downloads.push(String(parts[0])); } },
  setTimeout() {}, clearTimeout() {},
  console,
};
context.globalThis = context;

// 尾部追加导出：const/let 声明不会挂到 vm 的全局对象上，这里显式带出来
const epilogue = `
;globalThis.__t = { S, cfgTotalMs, cfgEls, endMs, totalMs, escapeHtml, saveScene, HAND_H_RATIO,
                    isText, textLines, drawTextBlock };
`;
vm.runInNewContext(source + epilogue, context, { filename: 'preview.html<script>' });
const t = context.__t;

// ---------- 1) 总时长 = 最后区域结束 + 0.5s，且能变短 ----------
const scene = ms => ({
  sceneDurationMs: 99999,   // 故意留一个过大的旧值
  elements: [
    { reveal: { startMs: 0, durationMs: 2000 } },
    { reveal: { startMs: 2200, durationMs: ms } },
  ],
});
assert.equal(t.cfgTotalMs(scene(2000)), 4700, '应为 2200+2000+500');
assert.ok(
  t.cfgTotalMs(scene(500)) < t.cfgTotalMs(scene(2000)),
  '缩短区域时长后总时长必须跟着变短（旧实现只增不减）',
);
assert.equal(t.cfgTotalMs({ elements: [] }), 1000, '无区域时给个最小时长');
assert.equal(t.cfgTotalMs({ elements: [], sceneDurationMs: 8000 }), 8000);

// ---------- 2) 保存：每个场景都要重算 sceneDurationMs，而不只当前场景 ----------
t.S.scenes = [
  { name: 'scene-01', cfgName: 'scene-01.annotation.json', cfg: scene(2000), cfgHandle: null },
  { name: 'scene-02', cfgName: 'scene-02.annotation.json', cfg: scene(1000), cfgHandle: null },
];
t.S.idx = 0;                       // 当前打开的是第 0 幕
t.S.dirty = new Set([0, 1]);
t.S.dirHandle = null;

await t.saveScene(1);              // 保存"非当前"场景
assert.equal(
  t.S.scenes[1].cfg.sceneDurationMs, 3700,
  '全部保存时，非当前场景的 sceneDurationMs 也必须重算（旧实现会写回 99999）',
);
await t.saveScene(0);
assert.equal(t.S.scenes[0].cfg.sceneDurationMs, 4700);
assert.equal(t.S.dirty.size, 0, '保存后应清掉 dirty 标记');
assert.equal(downloads.length, 2, '无文件句柄时应走下载兜底');
assert.ok(JSON.parse(downloads[0]).sceneDurationMs === 3700);

// ---------- 3) HTML 转义 ----------
const evil = '<img src=x onerror="alert(1)">';
const escaped = t.escapeHtml(evil);
assert.ok(!escaped.includes('<') && !escaped.includes('"'), '尖括号与引号都要转义');
assert.ok(escaped.includes('&lt;img'));

// ---------- 4) 场景名与手部素材：静态约束 ----------
assert.ok(
  source.includes('escapeHtml(s.name)'),
  '场景下拉列表必须对文件名做转义（曾直接插 ${s.name}）',
);
assert.ok(!/\$\{s\.name\}/.test(source), '不应再有未转义的 ${s.name}');
assert.equal(t.HAND_H_RATIO, 493 / 1080, '手部高度比例应与渲染器 Config 对齐');
assert.ok(
  !/w \/ 1672/.test(source),
  '手部叠加不应再假定画布宽度为 1672',
);

// ---------- 5) 文字区（标题 + 要点）----------
assert.equal(t.isText({ type: 'text' }), true);
assert.equal(t.isText({ type: 'object' }), false);
assert.equal(t.isText(null), false);

// text 可以是字符串，也可以是对象；bullets 允许写成单个字符串
// 注意：vm 里造出来的对象跨 realm，不能用 deepStrictEqual 比原型，逐字段比即可
const lines = e => { const r = t.textLines(e); return [r.title, r.subtitle, [...r.bullets].join('|')]; };
assert.deepEqual(lines({ text: '只有标题' }), ['只有标题', '', '']);
assert.deepEqual(lines({ text: { title: '标题', subtitle: '副标', bullets: ['一', '二'] } }), ['标题', '副标', '一|二']);
assert.deepEqual(lines({ text: { bullets: '就一条' } }), ['', '', '就一条']);
assert.deepEqual(lines({}), ['', '', '']);

// drawTextBlock 要真的往画布上写字：用一个记录调用的假 ctx
function recordingCtx() {
  const calls = { fillText: [], fillRect: 0, clipped: false, fonts: [] };
  return {
    calls,
    save() {}, restore() {}, beginPath() { }, clip() { calls.clipped = true; },
    rect() {}, fillRect() { calls.fillRect++; },
    fillText(text) { calls.fillText.push(text); },
    measureText(text) { return { width: text.length * 10 }; },
    set font(value) { calls.fonts.push(value); }, get font() { return ''; },
    set fillStyle(_v) {}, get fillStyle() { return ''; },
    set textBaseline(_v) {}, get textBaseline() { return ''; },
  };
}
const textElement = {
  type: 'text',
  region: { x: 20, y: 20, width: 400, height: 160 },
  text: { title: '本幕标题', subtitle: '封面副标', bullets: ['要点一', '要点二'] },
};
const ctx1 = recordingCtx();
t.drawTextBlock(ctx1, textElement);
assert.deepEqual([...ctx1.calls.fillText], ['本幕标题', '封面副标', '要点一', '要点二'], '标题、副标与要点都要画出来');
assert.ok(ctx1.calls.fillRect >= 3, '标题下划线 + 每条要点的短横');
assert.ok(ctx1.calls.clipped, '必须按区域裁剪，文字不能溢出区域');
assert.ok(ctx1.calls.fonts.some(f => /Kaiti|WenKai/.test(f)), '优先楷体/手写体字族');

// 空内容不应该画任何东西
const ctx2 = recordingCtx();
t.drawTextBlock(ctx2, { type: 'text', region: textElement.region, text: { title: '', bullets: [] } });
assert.equal(ctx2.calls.fillText.length, 0);

// 静态约束：新增文字区按钮、编辑控件、type 为 text 的模板
assert.ok(source.includes("type: 'text'"), '新增文字区要写 type: text');
assert.ok(/addTextBtn/.test(source), '要有"＋ 文字区"按钮');
assert.ok(/f_title|f_bullets/.test(source), '要有标题与要点的编辑控件');
assert.ok(source.includes('e.text.bullets = bullets'), '要点要写回 annotation');

console.log('preview.html: 5 组断言全部通过');
