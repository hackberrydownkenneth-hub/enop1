/**
 * 1ファイル版（standalone.html）を生成する。
 *
 *   node colormix/build.js
 *
 * CSS と JS を index.html に埋め込むだけ。生成物はスマホに送って
 * ダブルタップで開ける「配りやすい1ファイル」として使う。
 */
const fs = require("fs");
const path = require("path");

const dir = __dirname;
const read = (name) => fs.readFileSync(path.join(dir, name), "utf8");

const html = read("index.html");
const css = read("style.css");
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
