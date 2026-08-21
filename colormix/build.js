/**
 * 公開用の成果物を作る。
 *
 *   node colormix/build.js
 *
 * 1. colormix/standalone.html … CSS と JS を埋め込んだ配布用の1ファイル
 * 2. _site/ ……………………… ホスティングにそのまま載せる公開フォルダ
 *
 * Cloudflare Pages のビルドコマンドはこれ1行でよい（公開フォルダは _site）。
 */
const fs = require("fs");
const path = require("path");

const dir = __dirname;
const read = (name) => fs.readFileSync(path.join(dir, name), "utf8");

const html = read("index.html");

// 1ファイル版が外部ファイルを見に行かないよう、CSS 内の画像も data URI にする
const css = read("style.css").replace(/url\("([^"]+\.png)"\)/g, (whole, name) => {
  const file = path.join(dir, name);
  if (!fs.existsSync(file)) return whole;
  return 'url("data:image/png;base64,' + fs.readFileSync(file).toString("base64") + '")';
});
const i18n = read("i18n.js");
const calc = read("calc.js");
const profile = read("profile.js");
const config = read("config.js");
const app = read("app.js");
const register = read("register.js");

// インライン化する JS の中に </script> があるとそこで script が終わってしまう
const inlineScript = (source) =>
  "<script>\n" + source.trim().replace(/<\/script/gi, "<\\/script") + "\n    </script>";

const cssTag = '<link rel="stylesheet" href="style.css" />';
const scriptTags = [
  "i18n.js",
  "calc.js",
  "profile.js",
  "config.js",
  "app.js",
  "register.js",
]
  .map((name) => '<script src="' + name + '"></script>')
  .join("\n    ");

if (!html.includes(cssTag) || !html.includes(scriptTags)) {
  console.error("index.html の参照タグが見つかりません。build.js を更新してください。");
  process.exit(1);
}

const out = html
  .replace(cssTag, () => "<style>\n" + css.trim() + "\n    </style>")
  .replace(
    scriptTags,
    () => [i18n, calc, profile, config, app, register].map(inlineScript).join("\n    ")
  );

// data: 以外の外部参照が残っていたら 1ファイルとして成立しない
const leftover = out.match(/<(?:script|link)[^>]+(?:src|href)="(?!data:)[^"]+"/g);
if (leftover) {
  console.error("外部ファイルの参照が残っています: " + leftover.join(", "));
  process.exit(1);
}

fs.writeFileSync(path.join(dir, "standalone.html"), out);
console.log("colormix/standalone.html を生成しました (" + Math.round(out.length / 1024) + " KB)");

// 公開フォルダを作り直す。テストやビルド用のファイルは載せない
const siteDir = path.join(path.dirname(dir), "_site");
const published = [
  "index.html",
  "style.css",
  "i18n.js",
  "calc.js",
  "profile.js",
  "config.js",
  "app.js",
  "register.js",
  "logo.png",
  "logo-white.png",
  "_headers",
];

fs.rmSync(siteDir, { recursive: true, force: true });
fs.mkdirSync(siteDir, { recursive: true });
for (const name of published) {
  fs.copyFileSync(path.join(dir, name), path.join(siteDir, name));
}

// index.html が読み込むファイルが全部入っているか確かめる
const missing = [...html.matchAll(/(?:src|href)="(?!data:)([^"]+)"/g)]
  .map((match) => match[1])
  .filter((ref) => !published.includes(ref));
if (missing.length) {
  console.error("_site に入っていない参照があります: " + missing.join(", "));
  process.exit(1);
}

console.log("_site/ を生成しました (" + published.length + " ファイル)");
