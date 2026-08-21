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
    "app.docTitle": "カラー剤 計算機 | DRIVE BLUE HONG KONG",
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

    "footer.by": "提供",
    "footer.lead": "商品のご購入・お問い合わせはこちら",
    "footer.site": "公式サイト",
    "footer.instagram": "Instagram",
    "footer.aria.site": "DRIVE BLUE HONG KONG の公式サイトを開く",
    "footer.aria.instagram": "DRIVE BLUE HONG KONG の Instagram を開く",
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

    "reg.title": "はじめる前に",
    "reg.lead":
      "DRIVE BLUE HONG KONG がお届けする、美容師さん向けの無料ツールです。はじめて使うときだけ登録をお願いします（次回からは出ません）。",
    "reg.q1": "お仕事のスタイル",
    "reg.opt.salon": "サロン所属",
    "reg.opt.salon.sub": "お店に勤めている",
    "reg.opt.freelance": "フリーランス",
    "reg.opt.freelance.sub": "面貸し・独立・業務委託",
    "reg.salonName": "サロン名（任意）",
    "reg.salonName.ph": "例）SALON TOKYO",
    "reg.q2": "Instagram アカウント",
    "reg.q2.hint": "@ のあとのIDを入れてください。プロフィールのURLを貼ってもOK。",
    "reg.instagram.ph": "your_id",
    "reg.consent": "上の使いみちに同意します",
    "reg.purpose.collect":
      "いただいた情報（区分・サロン名・Instagram）は、運営者である DRIVE BLUE HONG KONG が、サービス改善・ご連絡・お知らせの配信のために使います。第三者には渡しません。",
    "reg.purpose.local":
      "※ プレビュー版です。入力した内容はこの端末の中だけに保存され、どこにも送信されません。",
    "reg.contact": "お問い合わせ: {contact}",
    "reg.submit": "同意してはじめる",
    "reg.submitting": "送信中…",
    "reg.err.affiliation": "お仕事のスタイルを選んでください",
    "reg.err.instagram": "Instagram の ID を入れてください",
    "reg.err.instagram_format": "使えるのは半角英数字と . _ です（30文字まで）",
    "reg.err.consent": "同意にチェックを入れてください",
    "reg.warn.offline": "いまは送信できませんでした。あとで自動的に送りなおします。",
    "reg.manage.title": "登録情報",
    "reg.aff.salon": "サロン所属",
    "reg.aff.freelance": "フリーランス",
    "reg.manage.delete": "この端末から削除",
    "reg.manage.deleted": "削除しました",
    "reg.manage.pending": "（未送信・あとで再送します）",

    "reg.done.title": "ありがとうございます！",
    "reg.done.lead":
      "WhatsApp でお知らせを受け取れます（任意）。ボタンを押すとメッセージが用意されるので、そのまま送信してください。",
    "reg.done.whatsapp": "WhatsApp で受け取る",
    "reg.done.start": "計算機をはじめる",
    "reg.whatsapp.message":
      "DRIVE BLUE の最新情報を受け取りたいです。Instagram: @{instagram}",
    "footer.whatsapp": "WhatsApp",
    "footer.aria.whatsapp": "DRIVE BLUE HONG KONG に WhatsApp で連絡する",
    "footer.whatsapp.message": "DRIVE BLUE の最新情報を受け取りたいです。",
  };

  var yue = {
    "lang.tag": "yue-Hant-HK",
    "lang.name": "廣東話",
    "app.title": "🎨 染髮劑計算機",
    "app.docTitle": "染髮劑計算機 | DRIVE BLUE HONG KONG",
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

    "footer.by": "提供",
    "footer.lead": "產品查詢・訂購",
    "footer.site": "官方網站",
    "footer.instagram": "Instagram",
    "footer.aria.site": "打開 DRIVE BLUE HONG KONG 官方網站",
    "footer.aria.instagram": "打開 DRIVE BLUE HONG KONG 嘅 Instagram",
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

    "reg.title": "開始之前",
    "reg.lead":
      "DRIVE BLUE HONG KONG 出品，美容師專用嘅免費工具。淨係第一次用要登記一次，之後唔會再出。",
    "reg.q1": "你嘅工作形式",
    "reg.opt.salon": "喺髮型屋返工",
    "reg.opt.salon.sub": "受聘於髮型屋",
    "reg.opt.freelance": "自由身",
    "reg.opt.freelance.sub": "租位、獨立、外判",
    "reg.salonName": "髮型屋名（可以唔填）",
    "reg.salonName.ph": "例：SALON HK",
    "reg.q2": "Instagram 帳戶",
    "reg.q2.hint": "入 @ 後面嘅 ID，貼個人檔案嘅 URL 都得。",
    "reg.instagram.ph": "your_id",
    "reg.consent": "我同意上面講嘅用途",
    "reg.purpose.collect":
      "你填嘅資料（工作形式、髮型屋名、Instagram）淨係會俾營運者 DRIVE BLUE HONG KONG 用嚟改善服務、聯絡你同 send 最新消息，唔會俾第三方。",
    "reg.purpose.local":
      "※ 呢個係預覽版。你填嘅嘢淨係擺喺呢部機入面，唔會傳去任何地方。",
    "reg.contact": "查詢: {contact}",
    "reg.submit": "同意，開始用",
    "reg.submitting": "傳送緊…",
    "reg.err.affiliation": "請揀你嘅工作形式",
    "reg.err.instagram": "請入 Instagram ID",
    "reg.err.instagram_format": "只可以用英文、數字同 . _（最多 30 個字）",
    "reg.err.consent": "請剔咗同意先",
    "reg.warn.offline": "而家傳送唔到，遲啲會自動再試。",
    "reg.manage.title": "登記資料",
    "reg.aff.salon": "喺髮型屋返工",
    "reg.aff.freelance": "自由身",
    "reg.manage.delete": "喺呢部機刪除",
    "reg.manage.deleted": "已刪除",
    "reg.manage.pending": "（未傳送・遲啲會再試）",

    "reg.done.title": "多謝！",
    "reg.done.lead":
      "可以用 WhatsApp 收最新消息（自願）。㩒個掣就會幫你打好訊息，直接 send 出嚟就得。",
    "reg.done.whatsapp": "用 WhatsApp 接收",
    "reg.done.start": "開始用計算機",
    "reg.whatsapp.message":
      "我想收 DRIVE BLUE 嘅最新消息。Instagram: @{instagram}",
    "footer.whatsapp": "WhatsApp",
    "footer.aria.whatsapp": "用 WhatsApp 聯絡 DRIVE BLUE HONG KONG",
    "footer.whatsapp.message": "我想收 DRIVE BLUE 嘅最新消息。",
  };

  var dictionaries = { ja: ja, yue: yue };
  var order = ["ja", "yue"];
  var LANG_KEY = "colormix.lang.v1";
  var listeners = [];
  var currentLang = null;

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

  function readStored() {
    try {
      return JSON.parse(localStorage.getItem(LANG_KEY));
    } catch (e) {
      return null;
    }
  }

  /** いま使う言語。保存済み → 端末の言語設定 → 日本語 の順に決まる */
  function current() {
    if (currentLang) return currentLang;
    var saved = readStored();
    currentLang = has(saved)
      ? saved
      : detect(
          (typeof navigator !== "undefined" &&
            (navigator.languages || [navigator.language])) ||
            []
        );
    return currentLang;
  }

  /** 言語を切り替えて、購読側（画面・登録フォーム）に知らせる */
  function set(lang) {
    if (!has(lang) || lang === current()) return;
    currentLang = lang;
    try {
      localStorage.setItem(LANG_KEY, JSON.stringify(lang));
    } catch (e) {
      /* 保存できなくても切り替えは効く */
    }
    listeners.forEach(function (fn) {
      fn(currentLang);
    });
  }

  function onChange(fn) {
    listeners.push(fn);
  }

  /** その言語で引く t() を作る */
  function scoped(getLang) {
    return function (key, params) {
      return translate(getLang(), key, params);
    };
  }

  return {
    LANGS: order,
    dictionaries: dictionaries,
    detect: detect,
    has: has,
    translate: translate,
    current: current,
    set: set,
    onChange: onChange,
    scoped: scoped,
  };
});
