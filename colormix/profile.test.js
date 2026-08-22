/**
 * 利用登録の入力チェックのテスト。
 *
 *   node --test colormix/profile.test.js
 */
const test = require("node:test");
const assert = require("node:assert");
const Profile = require("./profile.js");

test("Instagram の入力をIDだけに揃える", () => {
  const cases = [
    ["your_id", "your_id"],
    ["@your_id", "your_id"],
    ["  @Your_ID  ", "your_id"],
    ["@@your_id", "your_id"],
    ["https://www.instagram.com/foo.bar/", "foo.bar"],
    ["https://instagram.com/foo.bar?hl=ja", "foo.bar"],
    ["instagram.com/Foo_Bar/", "foo_bar"],
    ["http://www.instagram.com/foo/reels/", "foo"],
    ["", ""],
    [null, ""],
    [undefined, ""],
  ];
  for (const [input, expected] of cases) {
    assert.strictEqual(Profile.normalizeInstagram(input), expected, String(input));
  }
});

test("正しい入力は通る", () => {
  const result = Profile.validate({
    affiliation: "salon",
    salon: " SALON TOKYO ",
    instagram: "@Stylist.01",
    consent: true,
  });
  assert.strictEqual(result.ok, true);
  assert.deepStrictEqual(result.errors, {});
  assert.deepStrictEqual(result.value, {
    affiliation: "salon",
    salon: "SALON TOKYO",
    instagram: "stylist.01",
  });
});

test("フリーランスならサロン名は残さない", () => {
  const result = Profile.validate({
    affiliation: "freelance",
    salon: "入れても消える",
    instagram: "freelance_id",
    consent: true,
  });
  assert.strictEqual(result.ok, true);
  assert.strictEqual(result.value.salon, "");
});

test("区分・Instagram・同意はどれも必須", () => {
  const empty = Profile.validate({});
  assert.strictEqual(empty.ok, false);
  assert.deepStrictEqual(empty.errors, {
    affiliation: "affiliation",
    instagram: "instagram",
    consent: "consent",
  });

  assert.strictEqual(
    Profile.validate({ affiliation: "owner", instagram: "a", consent: true }).errors
      .affiliation,
    "affiliation"
  );
  assert.strictEqual(
    Profile.validate({ affiliation: "salon", instagram: "a", consent: false }).errors
      .consent,
    "consent"
  );
});

test("Instagram に使えない文字ははじく", () => {
  for (const handle of ["ダメな名前", "has space", "a".repeat(31), "foo!", "-foo-"]) {
    const result = Profile.validate({
      affiliation: "salon",
      instagram: handle,
      consent: true,
    });
    assert.strictEqual(result.ok, false, handle);
    assert.strictEqual(result.errors.instagram, "instagram_format", handle);
  }
  // 30文字ちょうどは通る
  assert.strictEqual(
    Profile.validate({
      affiliation: "salon",
      salon: "SALON TOKYO",
      instagram: "a" + "b".repeat(29),
      consent: true,
    }).ok,
    true
  );
  // スラッシュ以降は URL のパスとみなして落とす
  assert.strictEqual(Profile.normalizeInstagram("foo/bar"), "foo");
});

test("でたらめな Instagram の ID ははじく", () => {
  for (const handle of ["123", "111", "1234", "0000", "aaa", "ab", "test", "abc", ".foo", "foo.", "drive..blue"]) {
    const result = Profile.validate({
      affiliation: "freelance",
      instagram: handle,
      consent: true,
    });
    assert.strictEqual(result.ok, false, handle);
    assert.strictEqual(result.errors.instagram, "instagram_fake", handle);
  }
});

test("実在しそうな ID は通す", () => {
  // 一部だけの繰り返し・連番（driveblue111 / hellooo）は本物として通す
  for (const handle of [
    "kenneth_hk", "drive.blue", "a1b2c3", "hair_by_ken", "ken1",
    "driveblue111", "hellooo", "1111hair", "hair2000", "xxx_salon",
  ]) {
    const result = Profile.validate({
      affiliation: "freelance",
      instagram: handle,
      consent: true,
    });
    assert.strictEqual(result.ok, true, handle);
    assert.strictEqual(result.value.instagram, handle);
  }
});

test("サロン所属ならサロン名は必須", () => {
  const missing = Profile.validate({
    affiliation: "salon",
    salon: "   ",
    instagram: "stylist_id",
    consent: true,
  });
  assert.strictEqual(missing.ok, false);
  assert.strictEqual(missing.errors.salon, "salon");

  const filled = Profile.validate({
    affiliation: "salon",
    salon: "SALON TOKYO",
    instagram: "stylist_id",
    consent: true,
  });
  assert.strictEqual(filled.ok, true);
  assert.strictEqual(filled.errors.salon, undefined);
});

test("フリーランスはサロン名なしでも登録できる", () => {
  const result = Profile.validate({
    affiliation: "freelance",
    instagram: "stylist_id",
    consent: true,
  });
  assert.strictEqual(result.ok, true);
  assert.strictEqual(result.value.salon, "");
});

test("サロン名は80文字で切る", () => {
  const result = Profile.validate({
    affiliation: "salon",
    salon: "あ".repeat(200),
    instagram: "stylist_id",
    consent: true,
  });
  assert.strictEqual(result.value.salon.length, Profile.SALON_MAX);
});

test("送信レコードを組み立てる", () => {
  const { value } = Profile.validate({
    affiliation: "freelance",
    instagram: "@stylist_id",
    consent: true,
  });
  const record = Profile.buildRecord(value, { lang: "yue", registeredAt: "2026-08-21T00:00:00Z" });
  assert.deepStrictEqual(record, {
    affiliation: "freelance",
    salon: "",
    instagram: "stylist_id",
    lang: "yue",
    registeredAt: "2026-08-21T00:00:00Z",
  });
});

test("Google フォームの事前入力URLから送信設定を読み取る", () => {
  const url =
    "https://docs.google.com/forms/d/e/1FAIpQLSabc123/viewform?usp=pp_url" +
    "&entry.111111=affiliation&entry.222222=salon&entry.333333=instagram&entry.444444=lang";

  assert.deepStrictEqual(Profile.parseGoogleForm(url), {
    actionUrl: "https://docs.google.com/forms/d/e/1FAIpQLSabc123/formResponse",
    fields: {
      affiliation: "entry.111111",
      salon: "entry.222222",
      instagram: "entry.333333",
      lang: "entry.444444",
    },
  });
});

test("合言葉の大文字・空白・+ 表記を吸収する", () => {
  const url =
    "https://docs.google.com/forms/d/e/X/viewform?entry.1=+Affiliation+&entry.2=INSTAGRAM";
  assert.deepStrictEqual(Profile.parseGoogleForm(url).fields, {
    affiliation: "entry.1",
    instagram: "entry.2",
  });
});

test("サロン名と言語は無くても読み取れる（区分と Instagram は必須）", () => {
  const ok = Profile.parseGoogleForm(
    "https://docs.google.com/forms/d/e/X/viewform?entry.1=affiliation&entry.2=instagram"
  );
  assert.strictEqual(ok.fields.salon, undefined);

  const missing = Profile.parseGoogleForm(
    "https://docs.google.com/forms/d/e/X/viewform?entry.1=salon&entry.2=lang"
  );
  assert.strictEqual(missing, null, "区分と Instagram が無ければ設定なし扱い");
});

test("フォームのURLとして読めないものは null", () => {
  for (const bad of [
    "",
    null,
    undefined,
    "https://example.com/?entry.1=affiliation&entry.2=instagram",
    "https://docs.google.com/forms/d/e/X/viewform",
    "ただの文字列",
  ]) {
    assert.strictEqual(Profile.parseGoogleForm(bad), null, String(bad));
  }
});

test("回答用URLをそのまま貼っても動く", () => {
  const url =
    "https://docs.google.com/forms/d/e/X/formResponse?entry.1=affiliation&entry.2=instagram";
  assert.strictEqual(
    Profile.parseGoogleForm(url).actionUrl,
    "https://docs.google.com/forms/d/e/X/formResponse"
  );
});
