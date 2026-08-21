/**
 * 利用登録の入力チェック（画面から独立した純粋関数）。
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
    normalizeInstagram: normalizeInstagram,
    validate: validate,
    buildRecord: buildRecord,
  };
});
