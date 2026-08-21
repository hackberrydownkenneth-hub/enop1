/**
 * 配合計算のテスト。
 *
 *   node --test colormix/
 */
const test = require("node:test");
const assert = require("node:assert");
const ColorMix = require("./calc.js");

const items = (...parts) => parts.map((p, i) => ({ name: "剤" + i, parts: p }));
const grams = (result) => result.items.map((row) => row.grams);

test("1:1 の合計100g は 1剤50g / 2剤50g", () => {
  const r = ColorMix.calcFromTotal({ total: 100, oxRatio: 1, items: items(1) });
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.base1, 50);
  assert.strictEqual(r.ox, 50);
  assert.strictEqual(r.total, 100);
  assert.deepStrictEqual(grams(r), [50]);
});

test("1:2 の合計90g は 1剤30g / 2剤60g", () => {
  const r = ColorMix.calcFromTotal({ total: 90, oxRatio: 2, items: items(1) });
  assert.strictEqual(r.base1, 30);
  assert.strictEqual(r.ox, 60);
});

test("1:3 の合計120g は 1剤30g / 2剤90g", () => {
  const r = ColorMix.calcFromTotal({ total: 120, oxRatio: 3, items: items(1) });
  assert.strictEqual(r.base1, 30);
  assert.strictEqual(r.ox, 90);
});

test("1剤を 2:1 でミックスすると1剤の合計を按分する", () => {
  const r = ColorMix.calcFromTotal({ total: 120, oxRatio: 1, items: items(2, 1) });
  assert.strictEqual(r.base1, 60);
  assert.deepStrictEqual(grams(r), [40, 20]);
  assert.strictEqual(r.ox, 60);
});

test("1剤3種類でも配合比どおりに分ける", () => {
  const r = ColorMix.calcFromTotal({ total: 160, oxRatio: 1, items: items(4, 3, 1) });
  assert.strictEqual(r.base1, 80);
  assert.deepStrictEqual(grams(r), [40, 30, 10]);
});

test("割り切れなくても1剤の合計はぴったり一致する（1g刻み）", () => {
  const r = ColorMix.calcFromTotal({ total: 100, oxRatio: 2, items: items(1, 1, 1) });
  assert.strictEqual(r.base1, 33);
  assert.strictEqual(r.ox, 67);
  assert.strictEqual(r.total, 100, "合計は入力どおり100g");
  const sum = grams(r).reduce((a, b) => a + b, 0);
  assert.strictEqual(sum, r.base1, "各1剤の合計 = 1剤の合計");
  assert.deepStrictEqual(grams(r), [11, 11, 11]);
});

test("0.1g刻みでも合計が一致する", () => {
  const r = ColorMix.calcFromTotal({
    total: 100,
    oxRatio: 2,
    items: items(2, 1),
    step: 0.1,
  });
  assert.strictEqual(r.base1, 33.3);
  assert.strictEqual(r.ox, 66.7);
  assert.strictEqual(r.total, 100);
  const sum = grams(r).reduce((a, b) => a + b, 0);
  assert.ok(Math.abs(sum - r.base1) < 1e-9);
  assert.deepStrictEqual(
    r.items.map((row) => row.text),
    ["22.2", "11.1"]
  );
});

test("1:1.5 のような小数倍率も扱える", () => {
  const r = ColorMix.calcFromTotal({ total: 100, oxRatio: 1.5, items: items(1) });
  assert.strictEqual(r.base1, 40);
  assert.strictEqual(r.ox, 60);
});

test("2剤なし（倍率0）は全量が1剤", () => {
  const r = ColorMix.calcFromTotal({ total: 50, oxRatio: 0, items: items(1) });
  assert.strictEqual(r.base1, 50);
  assert.strictEqual(r.ox, 0);
});

test("刻みに合わない合計量は丸めて adjusted を立てる", () => {
  const r = ColorMix.calcFromTotal({ total: 100.4, oxRatio: 1, items: items(1) });
  assert.strictEqual(r.total, 100);
  assert.strictEqual(r.adjusted, true);
});

test("1剤量モード: 30g+10g を 1:2 で使うと2剤80g・合計120g", () => {
  const r = ColorMix.calcFromBase({
    oxRatio: 2,
    items: [
      { name: "ブラウン", grams: 30 },
      { name: "マット", grams: 10 },
    ],
  });
  assert.strictEqual(r.base1, 40);
  assert.strictEqual(r.ox, 80);
  assert.strictEqual(r.total, 120);
  assert.deepStrictEqual(grams(r), [30, 10]);
});

test("追い足し: 合計120g の 5% は 6g、総量は126g", () => {
  const r = ColorMix.calcFromTotal({
    total: 120,
    oxRatio: 2,
    items: items(1),
    addOnPercent: 5,
  });
  assert.strictEqual(r.base1, 40);
  assert.strictEqual(r.ox, 80);
  assert.strictEqual(r.total, 120, "追い足し前の合計は変わらない");
  assert.strictEqual(r.addOn.grams, 6);
  assert.strictEqual(r.base1WithAddOn, 46);
  assert.strictEqual(r.grandTotal, 126);
  assert.strictEqual(r.items[0].withAddOn, 46);
});

test("追い足しも配合比どおりに割り振り、合計はぴったり一致する", () => {
  const r = ColorMix.calcFromTotal({
    total: 120,
    oxRatio: 2,
    items: items(2, 1),
    addOnPercent: 10,
  });
  assert.strictEqual(r.addOn.grams, 12);
  assert.deepStrictEqual(r.addOn.items.map((row) => row.grams), [8, 4]);
  const sum = r.addOn.items.reduce((a, row) => a + row.grams, 0);
  assert.strictEqual(sum, r.addOn.grams);
  assert.deepStrictEqual(r.items.map((row) => row.withAddOn), [35, 17]);
  assert.strictEqual(r.grandTotal, 132);
});

test("追い足しは1剤量モードでも合計量を基準にする", () => {
  const r = ColorMix.calcFromBase({
    oxRatio: 1,
    items: [{ grams: 50 }],
    addOnPercent: 10,
  });
  assert.strictEqual(r.total, 100);
  assert.strictEqual(r.addOn.grams, 10, "合計100g の10%");
  assert.strictEqual(r.grandTotal, 110);
});

test("追い足しは0.1g刻みでも端数が消えない", () => {
  const r = ColorMix.calcFromTotal({
    total: 100,
    oxRatio: 2,
    items: items(2, 1),
    addOnPercent: 7,
    step: 0.1,
  });
  assert.strictEqual(r.addOn.grams, 7);
  assert.deepStrictEqual(r.addOn.items.map((row) => row.text), ["4.7", "2.3"]);
  assert.strictEqual(r.grandTotal, 107);
});

test("追い足しなし・不正な％は addOn が null で総量は合計のまま", () => {
  for (const pct of [undefined, 0, -5, NaN, "abc"]) {
    const r = ColorMix.calcFromTotal({
      total: 100,
      oxRatio: 1,
      items: items(1),
      addOnPercent: pct,
    });
    assert.strictEqual(r.addOn, null, String(pct));
    assert.strictEqual(r.grandTotal, 100);
    assert.strictEqual(r.base1WithAddOn, r.base1);
    assert.strictEqual(r.items[0].withAddOn, r.items[0].grams);
  }
});

test("追い足しの％は100%までに丸める", () => {
  const r = ColorMix.calcFromTotal({
    total: 100,
    oxRatio: 1,
    items: items(1),
    addOnPercent: 500,
  });
  assert.strictEqual(r.addOn.percent, 100);
  assert.strictEqual(r.addOn.grams, 100);
});

test("配分は合計が必ず一致する（総当たり）", () => {
  for (let total = 1; total <= 200; total++) {
    for (const parts of [[1, 1], [2, 1], [3, 2, 1], [5, 3, 3, 1], [7]]) {
      const allocated = ColorMix.distribute(total, parts);
      const sum = allocated.reduce((a, b) => a + b, 0);
      assert.strictEqual(sum, total, `total=${total} parts=${parts}`);
      assert.ok(allocated.every((v) => v >= 0));
    }
  }
});

test("入力が足りないときはエラーコードを返す（文言は画面側で翻訳）", () => {
  const cases = [
    [ColorMix.calcFromTotal({ total: 0, oxRatio: 1, items: items(1) }), "need_total"],
    [ColorMix.calcFromTotal({ total: 100, oxRatio: 1, items: [] }), "need_item"],
    [ColorMix.calcFromTotal({ total: 100, oxRatio: 1, items: items(0, 0) }), "need_parts"],
    [ColorMix.calcFromTotal({ total: 100, oxRatio: -1, items: items(1) }), "need_ratio"],
    [ColorMix.calcFromTotal({ total: 0.4, oxRatio: 1, items: items(1) }), "total_too_small"],
    [ColorMix.calcFromBase({ oxRatio: 2, items: [{ grams: 0 }] }), "need_grams"],
  ];
  for (const [result, code] of cases) {
    assert.strictEqual(result.ok, false);
    assert.strictEqual(result.code, code);
  }
});

test("calc は mode で振り分ける", () => {
  const a = ColorMix.calc({ mode: "total", total: 100, oxRatio: 1, items: items(1) });
  const b = ColorMix.calc({ mode: "base", oxRatio: 1, items: [{ grams: 50 }] });
  assert.strictEqual(a.total, 100);
  assert.strictEqual(b.total, 100);
});
