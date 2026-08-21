/**
 * 画面の文言（日本語 / 廣東話）。
 *
 * ブラウザ: script タグで読み込むと window.ColorMixI18N から参照できる
 *
 * ・{name} は置換用のプレースホルダ
 * ・**強調** は <b> になる（innerHTML は使わない）
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.ColorMixI18N = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var ja = {
    "lang.tag": "ja",
    "lang.name": "日本語",
    "app.title": "🎨 カラー剤 計算機",
    "app.docTitle": "カラー剤 計算機",
    "app.tagline": "タップするだけ。1剤のグラム数を自動で出します。",
    "lang.aria": "言語",

    "tabs.aria": "計算のしかた",
    "tab.total.title": "合計量からきめる",
    "tab.total.sub": "ぜんぶで◯g つくりたい",
    "tab.base.title": "1剤の量からきめる",
    "tab.base.sub": "1剤を◯g 使いたい",

    "step1.title": "2剤のわりあい",
    "step1.hint": "1剤 1 に対して、2剤（オキシ）を何倍いれる？",
    "step1.custom": "その他の倍率",
    "step1.aria.input": "2剤の倍率",
    "step1.aria.minus": "倍率を減らす",
    "step1.aria.plus": "倍率を増やす",
    "step1.ratioLabel": "1剤 : 2剤 ＝ ",

    "step2.title": "ぜんぶで何g つくる？",
    "step2.hint": "1剤と2剤をまぜたあとの合計量です。",
    "step2.label": "合計量",
    "step2.aria.input": "合計量（g）",
    "step2.aria.minus": "10g 減らす",
    "step2.aria.plus": "10g 増やす",

    "items.title.total": "1剤のミックス",
    "items.title.base": "使う1剤の量",
    "items.hint.total":
      "まぜる1剤の「わりあい」を入れてください（例 2 : 1）。1種類だけならそのままでOK。",
    "items.hint.base":
      "実際にはかる1剤のグラム数を入れてください。2剤と合計量を計算します。",
    "items.add": "＋ 1剤をふやす",
    "item.placeholder": "1剤 {n}（例 ブラウン6）",
    "item.fallback": "1剤 {n}",
    "item.aria.name": "{n}番目の1剤の名前",
    "item.aria.del": "{n}番目の1剤を削除",
    "item.aria.value": "{n}番目の{label}",
    "item.aria.minus": "減らす",
    "item.aria.plus": "増やす",
    "label.parts": "わりあい",
    "label.grams": "使う量",

    "result.title": "はかる量",
    "result.partsSub": "わりあい {parts}（全体の {pct}%）",
    "result.subtotal": "1剤 合計 {g}g",
    "result.ox": "2剤（オキシ）",
    "result.oxSub": "1剤の {r} 倍",
    "result.sum": "ぜんぶで",
    "result.notice": "※ {req}g は {step} 刻みに丸めて {got}g で計算しました。",
    "step.label": "はかる細かさ",
    "step.1": "1g刻み",
    "step.0.1": "0.1g刻み",

    "action.copy": "📋 コピー",
    "action.save": "⭐ レシピ保存",
    "action.reset": "↺ リセット",

    "recipes.title": "保存したレシピ",
    "recipe.aria.del": "{name} を削除",

    "how.summary": "つかいかた・計算のしくみ",
    "how.step1": "**2剤のわりあい**を選ぶ（1:1 / 1:2 / 1:3 など）",
    "how.step2": "**ぜんぶで何g** つくるか入れる",
    "how.step3": "まぜる**1剤のわりあい**を入れる（例 ブラウン 2 : マット 1）",
    "how.math":
      "1剤の合計 ＝ 合計量 ÷（1 ＋ 2剤の倍率）\n2剤 ＝ 合計量 − 1剤の合計\n各1剤 ＝ 1剤の合計 × その割合 ÷ 割合の合計",
    "how.note1":
      "例）合計 90g で 1:2 のとき → 1剤 30g、2剤 60g。1剤を 2:1 でまぜるなら 20g と 10g。",
    "how.note2":
      "小数が出る場合はグラム数を丸めますが、**合計量はいつもぴったり**になるよう調整しています。0.1g 単位ではかりたいときは、結果の下の「0.1g刻み」を選んでください。",

    "sticky.base": "1剤",
    "sticky.ox": "2剤",
    "sticky.total": "合計",

    "err.need_total": "つくる合計量を入力してください",
    "err.need_ratio": "2剤の倍率を入力してください",
    "err.need_item": "1剤を1つ以上追加してください",
    "err.need_parts": "1剤の配合比を入力してください",
    "err.total_too_small": "合計量が少なすぎます",
    "err.base_too_small": "合計量が少なすぎて1剤が計れません",
    "err.need_grams": "1剤の量を入力してください",

    "toast.copied": "コピーしました",
    "toast.copy_failed": "コピーできませんでした",
    "toast.need_input": "先に入力してください",
    "toast.saved": "保存しました",
    "toast.loaded": "よびだしました",

    "prompt.save": "レシピの名前をつけてください",
    "confirm.reset": "入力をリセットしますか？（保存したレシピは消えません）",

    "copy.header": "【カラーレシピ】",
    "copy.ratio": "1剤 : 2剤 ＝ ",
    "copy.subtotal": "1剤 合計",
    "copy.ox": "2剤",
    "copy.total": "ぜんぶで",
  };

  var yue = {
    "lang.tag": "yue-Hant-HK",
    "lang.name": "廣東話",
    "app.title": "🎨 染髮劑計算機",
    "app.docTitle": "染髮劑計算機",
    "app.tagline": "撳幾下就得，自動計出每支染膏要幾多 g。",
    "lang.aria": "語言",

    "tabs.aria": "計算方式",
    "tab.total.title": "用總份量計",
    "tab.total.sub": "想溝夠 ◯g",
    "tab.base.title": "用染膏份量計",
    "tab.base.sub": "想用 ◯g 染膏",

    "step1.title": "雙氧奶嘅比例",
    "step1.hint": "染膏 1 份，要落幾多倍雙氧奶（二劑）？",
    "step1.custom": "其他倍數",
    "step1.aria.input": "雙氧奶嘅倍數",
    "step1.aria.minus": "減少倍數",
    "step1.aria.plus": "增加倍數",
    "step1.ratioLabel": "染膏 : 雙氧奶 ＝ ",

    "step2.title": "總共要溝幾多 g？",
    "step2.hint": "即係染膏加雙氧奶溝埋之後嘅總份量。",
    "step2.label": "總份量",
    "step2.aria.input": "總份量（g）",
    "step2.aria.minus": "減 10g",
    "step2.aria.plus": "加 10g",

    "items.title.total": "染膏點溝",
    "items.title.base": "用幾多染膏",
    "items.hint.total":
      "入低每支染膏嘅「比例」（例：2 : 1）。淨係用一支就唔使改。",
    "items.hint.base":
      "入低你實際要秤嘅染膏 g 數，會計返雙氧奶同總份量。",
    "items.add": "＋ 加多支染膏",
    "item.placeholder": "染膏 {n}（例：啡色 6）",
    "item.fallback": "染膏 {n}",
    "item.aria.name": "第 {n} 支染膏嘅名",
    "item.aria.del": "刪除第 {n} 支染膏",
    "item.aria.value": "第 {n} 支嘅{label}",
    "item.aria.minus": "減少",
    "item.aria.plus": "增加",
    "label.parts": "比例",
    "label.grams": "份量",

    "result.title": "要秤幾多",
    "result.partsSub": "比例 {parts}（佔 {pct}%）",
    "result.subtotal": "染膏合計 {g}g",
    "result.ox": "雙氧奶（二劑）",
    "result.oxSub": "染膏嘅 {r} 倍",
    "result.sum": "總共",
    "result.notice": "※ {req}g 已經按 {step} 為單位調整做 {got}g 嚟計。",
    "step.label": "秤嘅精度",
    "step.1": "1g 為單位",
    "step.0.1": "0.1g 為單位",

    "action.copy": "📋 複製",
    "action.save": "⭐ 儲存配方",
    "action.reset": "↺ 重設",

    "recipes.title": "已儲存嘅配方",
    "recipe.aria.del": "刪除 {name}",

    "how.summary": "用法・點計出嚟",
    "how.step1": "揀**雙氧奶嘅比例**（1:1 / 1:2 / 1:3 等等）",
    "how.step2": "入**總共要溝幾多 g**",
    "how.step3": "入**每支染膏嘅比例**（例：啡色 2 : 冷色 1）",
    "how.math":
      "染膏合計 ＝ 總份量 ÷（1 ＋ 雙氧奶倍數）\n雙氧奶 ＝ 總份量 － 染膏合計\n每支染膏 ＝ 染膏合計 × 佢嘅比例 ÷ 比例總和",
    "how.note1":
      "例：總共 90g、1:2 → 染膏 30g、雙氧奶 60g。染膏用 2:1 溝，就係 20g 同 10g。",
    "how.note2":
      "有小數會四捨五入，但**總份量一定啱數**。想秤到 0.1g，就揀結果下面嘅「0.1g 為單位」。",

    "sticky.base": "染膏",
    "sticky.ox": "雙氧奶",
    "sticky.total": "總共",

    "err.need_total": "請入總份量",
    "err.need_ratio": "請入雙氧奶倍數",
    "err.need_item": "最少要有一支染膏",
    "err.need_parts": "請入染膏嘅比例",
    "err.total_too_small": "總份量太少",
    "err.base_too_small": "總份量太少，秤唔到染膏",
    "err.need_grams": "請入染膏份量",

    "toast.copied": "已複製",
    "toast.copy_failed": "複製唔到",
    "toast.need_input": "請先輸入",
    "toast.saved": "已儲存",
    "toast.loaded": "已載入",

    "prompt.save": "幫呢個配方改個名",
    "confirm.reset": "要重設所有輸入？（已儲存嘅配方唔會刪除）",

    "copy.header": "【染髮配方】",
    "copy.ratio": "染膏 : 雙氧奶 ＝ ",
    "copy.subtotal": "染膏合計",
    "copy.ox": "雙氧奶",
    "copy.total": "總共",
  };

  var dictionaries = { ja: ja, yue: yue };
  var order = ["ja", "yue"];

  /** 端末の言語設定から初期言語を決める */
  function detect(languages) {
    var list = languages || [];
    for (var i = 0; i < list.length; i++) {
      var tag = String(list[i]).toLowerCase();
      if (tag.indexOf("yue") === 0 || tag.indexOf("zh") === 0) return "yue";
      if (tag.indexOf("ja") === 0) return "ja";
    }
    return "ja";
  }

  function has(lang) {
    return order.indexOf(lang) >= 0;
  }

  /** キーを引いて {name} を差し替える。未定義キーは日本語 → キー名の順にフォールバック */
  function translate(lang, key, params) {
    var dict = dictionaries[has(lang) ? lang : "ja"];
    var text = dict[key];
    if (text === undefined) text = ja[key];
    if (text === undefined) return key;
    if (!params) return text;
    return text.replace(/\{(\w+)\}/g, function (match, name) {
      return Object.prototype.hasOwnProperty.call(params, name)
        ? String(params[name])
        : match;
    });
  }

  return {
    LANGS: order,
    dictionaries: dictionaries,
    detect: detect,
    has: has,
    translate: translate,
  };
});
