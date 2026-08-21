/**
 * 文言辞書の健全性チェック。
 *
 *   node --test colormix/i18n.test.js
 *
 * 片方の言語だけ直して、もう片方に日本語が残る事故を防ぐ。
 */
const test = require("node:test");
const assert = require("node:assert");
const I18N = require("./i18n.js");

const { ja, yue } = I18N.dictionaries;

// 両言語で同じ文字列になるのが自然なキー
const SHARED_ON_PURPOSE = new Set([
  "footer.by", // 「提供」は日本語・繁体字とも同じ
  "footer.instagram", // サービス名
  "reg.instagram.ph", // 入力例
  "footer.whatsapp", // サービス名
  "reg.done.whatsapp", // 英字のボタン文言（両言語で共通にしている）
]);

test("キーが両言語で揃っている", () => {
  // 空文字を持つキー（意図的に文言を消したもの）を「無い」と誤判定しないよう、
  // 値の真偽ではなくキーの有無で見る
  const has = (dict, key) => Object.prototype.hasOwnProperty.call(dict, key);
  assert.deepStrictEqual(
    Object.keys(ja).filter((k) => !has(yue, k)),
    [],
    "繁體中文に無いキー"
  );
  assert.deepStrictEqual(
    Object.keys(yue).filter((k) => !has(ja, k)),
    [],
    "日本語に無いキー"
  );
});

test("翻訳し忘れ（両言語で同じ文言）が無い", () => {
  const same = Object.keys(ja).filter(
    (key) => ja[key] !== "" && ja[key] === yue[key] && !SHARED_ON_PURPOSE.has(key)
  );
  assert.deepStrictEqual(same, [], "繁體中文が日本語のままになっているキー");
});

test("繁體中文に日本語のかなが混ざっていない", () => {
  // 中黒(U+30FB)は繁体字でも区切りに使うので、かなの判定から外す
  const kana = /[\u3041-\u309F\u30A1-\u30FA\u30FC-\u30FF]/;
  const leaked = Object.keys(yue).filter((key) => kana.test(yue[key]));
  assert.deepStrictEqual(leaked, [], "ひらがな・カタカナが残っているキー");
});

test("置換用の {name} が両言語で一致している", () => {
  const holders = (text) => (String(text).match(/\{(\w+)\}/g) || []).sort();
  for (const key of Object.keys(ja)) {
    assert.deepStrictEqual(holders(yue[key]), holders(ja[key]), key);
  }
});

test("エラーコードに対応する文言が揃っている", () => {
  const codes = [
    "need_total",
    "need_ratio",
    "need_item",
    "need_parts",
    "total_too_small",
    "base_too_small",
    "need_grams",
  ];
  for (const code of codes) {
    for (const lang of I18N.LANGS) {
      const text = I18N.translate(lang, "err." + code);
      assert.notStrictEqual(text, "err." + code, `${lang} の err.${code} が無い`);
    }
  }
});

test("未定義のキーは日本語 → キー名の順にフォールバックする", () => {
  assert.strictEqual(I18N.translate("yue", "app.docTitle").length > 0, true);
  assert.strictEqual(I18N.translate("yue", "存在しないキー"), "存在しないキー");
  assert.strictEqual(I18N.translate("klingon", "footer.site"), ja["footer.site"]);
});

test("端末の言語から初期言語を決める", () => {
  assert.strictEqual(I18N.detect(["zh-HK", "en"]), "yue");
  assert.strictEqual(I18N.detect(["yue-Hant-HK"]), "yue");
  assert.strictEqual(I18N.detect(["ja-JP"]), "ja");
  assert.strictEqual(I18N.detect(["en-US"]), "ja");
  assert.strictEqual(I18N.detect([]), "ja");
});
