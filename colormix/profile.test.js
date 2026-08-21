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
    Profile.validate({ affiliation: "salon", instagram: "a".repeat(30), consent: true }).ok,
    true
  );
  // スラッシュ以降は URL のパスとみなして落とす
  assert.strictEqual(Profile.normalizeInstagram("foo/bar"), "foo");
});

test("サロン名は80文字で切る", () => {
  const result = Profile.validate({
    affiliation: "salon",
    salon: "あ".repeat(200),
    instagram: "id",
    consent: true,
  });
  assert.strictEqual(result.value.salon.length, Profile.SALON_MAX);
});

test("送信レコードを組み立てる", () => {
  const { value } = Profile.validate({
    affiliation: "freelance",
    instagram: "@id",
    consent: true,
  });
  const record = Profile.buildRecord(value, { lang: "yue", registeredAt: "2026-08-21T00:00:00Z" });
  assert.deepStrictEqual(record, {
    affiliation: "freelance",
    salon: "",
    instagram: "id",
    lang: "yue",
    registeredAt: "2026-08-21T00:00:00Z",
  });
});
