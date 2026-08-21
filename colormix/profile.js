/**
 * 利用登録まわりの純粋関数（画面から独立）。
 *
 * ・入力チェック（validate / normalizeInstagram）
 * ・Google フォームの「事前入力したURL」から送信設定を読み取る（parseGoogleForm）
 *
 * ブラウザ: script タグで読み込むと window.ColorMixProfile から参照できる
 * Node    : require("./profile.js")
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.ColorMixProfile = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var AFFILIATIONS = ["salon", "freelance"];
  var HANDLE_RE = /^[a-z0-9._]{1,30}$/;
  var SALON_MAX = 80;

  /**
   * 入力された Instagram アカウントを ID だけに揃える。
   * "@Foo_Bar" も "https://www.instagram.com/foo.bar/?hl=ja" も "foo.bar" になる。
   */
  function normalizeInstagram(raw) {
    var text = String(raw === undefined || raw === null ? "" : raw).trim();
    if (!text) return "";

    var match = text.match(/instagram\.com\/([^/?#]+)/i);
    if (match) {
      text = match[1];
    } else {
      // URL ではないので @ とゴミだけ落とす
      text = text.replace(/^https?:\/\//i, "").replace(/^@+/, "");
      text = text.split(/[/?#]/)[0];
    }
    return text.trim().replace(/^@+/, "").toLowerCase();
  }

  function trimTo(value, max) {
    return String(value === undefined || value === null ? "" : value)
      .trim()
      .slice(0, max);
  }

  /**
   * 登録フォームの入力を検証する。
   * @returns {{ok: boolean, errors: object, value: object}}
   *          errors は { instagram: "instagram_format" } のようなコード。
   */
  function validate(input) {
    var data = input || {};
    var errors = {};

    var affiliation = data.affiliation;
    if (AFFILIATIONS.indexOf(affiliation) < 0) {
      errors.affiliation = "affiliation";
      affiliation = "";
    }

    var instagram = normalizeInstagram(data.instagram);
    if (!instagram) {
      errors.instagram = "instagram";
    } else if (!HANDLE_RE.test(instagram)) {
      errors.instagram = "instagram_format";
    }

    if (data.consent !== true) {
      errors.consent = "consent";
    }

    return {
      ok: Object.keys(errors).length === 0,
      errors: errors,
      value: {
        affiliation: affiliation,
        // サロン所属のときだけ店名を残す
        salon: affiliation === "salon" ? trimTo(data.salon, SALON_MAX) : "",
        instagram: instagram,
      },
    };
  }

  // 事前入力URLの各欄に入れてもらう合言葉。この値で項目を見分ける
  var FORM_KEYS = ["affiliation", "salon", "instagram", "lang"];

  /**
   * Google フォームの「事前入力したURLを取得」で出てくるURLから、
   * 送信先と entry.xxx の対応を読み取る。
   *
   * 各欄に affiliation / salon / instagram / lang と入れておくと、
   * どの entry がどの項目かを値から判定できるので、IDを手で調べる必要がない。
   *
   * @returns {{actionUrl: string, fields: object}|null} 読み取れなければ null
   */
  function parseGoogleForm(prefilledUrl) {
    var text = String(prefilledUrl === undefined || prefilledUrl === null ? "" : prefilledUrl).trim();
    var mark = text.indexOf("?");
    if (mark < 0) return null;

    var actionUrl = text.slice(0, mark).replace(/\/viewform$/, "/formResponse");
    if (!/\/formResponse$/.test(actionUrl)) return null;

    var fields = {};
    text
      .slice(mark + 1)
      .split("&")
      .forEach(function (pair) {
        var eq = pair.indexOf("=");
        if (eq < 0) return;
        var key = pair.slice(0, eq);
        if (key.indexOf("entry.") !== 0) return;
        var value = decodeURIComponent(pair.slice(eq + 1).replace(/\+/g, " "))
          .trim()
          .toLowerCase();
        if (FORM_KEYS.indexOf(value) >= 0 && !fields[value]) fields[value] = key;
      });

    // 区分と Instagram が取れないと登録の意味がないので、設定なし扱いにする
    if (!fields.affiliation || !fields.instagram) return null;
    return { actionUrl: actionUrl, fields: fields };
  }

  /** 保存・送信する形に整える */
  function buildRecord(value, meta) {
    var extra = meta || {};
    return {
      affiliation: value.affiliation,
      salon: value.salon || "",
      instagram: value.instagram,
      lang: extra.lang || "",
      registeredAt: extra.registeredAt || "",
    };
  }

  return {
    AFFILIATIONS: AFFILIATIONS,
    SALON_MAX: SALON_MAX,
    FORM_KEYS: FORM_KEYS,
    normalizeInstagram: normalizeInstagram,
    parseGoogleForm: parseGoogleForm,
    validate: validate,
    buildRecord: buildRecord,
  };
});
