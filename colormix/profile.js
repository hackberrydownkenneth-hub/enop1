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
   * 明らかに実在しない入力（123 / 111 / test など）を弾くための決まり。
   * Instagram の実在確認まではできないので、ここでは「まず本物ではない」
   * ものだけを落とす。
   */
  var HANDLE_MIN = 3;
  var JUNK_HANDLES = [
    "abc", "abcd", "abcde", "asd", "asdf", "asdfgh", "qwe", "qwer", "qwerty",
    "test", "tester", "testing", "tests", "sample", "example", "demo", "dummy",
    "none", "nothing", "null", "nil", "nan", "unknown", "anonymous", "anon",
    "user", "users", "guest", "hello", "hi", "hey", "me", "you", "my", "mine",
    "ig", "insta", "instagram", "private", "secret", "no", "nope", "yes", "ok",
    "aaa", "bbb", "ccc", "xxx", "yyy", "zzz", "www", "qaz", "zxc",
  ];

  /** 「1」「a」だけの繰り返し（111 / aaaa / .... など） */
  function isRepeated(text) {
    return /^(.)\1*$/.test(text);
  }

  /** 連番（123 / 1234 / abcd の並び） */
  function isSequential(text) {
    if (text.length < 3) return false;
    var up = 0;
    var down = 0;
    for (var i = 1; i < text.length; i++) {
      var diff = text.charCodeAt(i) - text.charCodeAt(i - 1);
      if (diff === 1) up++;
      else if (diff === -1) down++;
    }
    return up === text.length - 1 || down === text.length - 1;
  }

  /**
   * 形は正しくても、中身が明らかにでたらめかどうか。
   * true なら登録させない。
   */
  function looksFake(handle) {
    if (!handle) return false;
    if (handle.length < HANDLE_MIN) return true;
    // 記号だけ、数字だけは実在アカウントとして扱わない
    if (!/[a-z]/.test(handle)) return true;
    if (isRepeated(handle)) return true;
    if (isSequential(handle)) return true;
    if (JUNK_HANDLES.indexOf(handle) >= 0) return true;
    // Instagram は先頭・末尾のピリオド、ピリオドの連続を認めていない
    if (handle.charAt(0) === "." || handle.charAt(handle.length - 1) === ".") {
      return true;
    }
    if (handle.indexOf("..") >= 0) return true;
    return false;
  }

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

    // サロン所属を選んだときは店名が必須
    var salon = trimTo(data.salon, SALON_MAX);
    if (affiliation === "salon" && !salon) {
      errors.salon = "salon";
    }

    var instagram = normalizeInstagram(data.instagram);
    if (!instagram) {
      errors.instagram = "instagram";
    } else if (!HANDLE_RE.test(instagram)) {
      errors.instagram = "instagram_format";
    } else if (looksFake(instagram)) {
      errors.instagram = "instagram_fake";
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
        salon: affiliation === "salon" ? salon : "",
        instagram: instagram,
      },
    };
  }

  // 事前入力URLの各欄に入れてもらう合言葉。この値で項目を見分ける
  var FORM_KEYS = ["affiliation", "salon", "instagram", "lang"];
  var FORM_REQUIRED = ["affiliation", "instagram"];

  /**
   * Google フォームの「事前入力したURLを取得」で出てくるURLから、
   * 送信先と entry.xxx の対応を読み取る。
   *
   * 各欄に affiliation / salon / instagram / lang と入れておくと、
   * どの entry がどの項目かを値から判定できるので、IDを手で調べる必要がない。
   *
   * 改善のご要望フォームのように別の項目を読み取りたいときは、
   * options で合言葉（keys）と必須の項目（required）を渡す。
   *
   * @returns {{actionUrl: string, fields: object}|null} 読み取れなければ null
   */
  function parseGoogleForm(prefilledUrl, options) {
    var opts = options || {};
    var keys = opts.keys || FORM_KEYS;
    var required = opts.required || FORM_REQUIRED;
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
        if (keys.indexOf(value) >= 0 && !fields[value]) fields[value] = key;
      });

    // 必須の項目が取れないと送っても意味がないので、設定なし扱いにする
    for (var i = 0; i < required.length; i++) {
      if (!fields[required[i]]) return null;
    }
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
    looksFake: looksFake,
    parseGoogleForm: parseGoogleForm,
    validate: validate,
    buildRecord: buildRecord,
  };
});
