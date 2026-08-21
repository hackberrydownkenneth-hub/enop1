/**
 * 配置ごとの設定。ここだけ書き換えれば送信先を変えられる。
 *
 * register.mode
 *   "off"   … 登録画面を出さない（社内配布・1ファイル版など）
 *   "local" … 登録画面は出すが、入力はこの端末にだけ保存（プレビュー用）
 *   "api"   … 自前サーバー（colormix_server）へ JSON で送る
 *   "form"  … Google フォームへ送る（サーバー不要。回答はスプレッドシートに溜まる）
 */
window.COLORMIX_CONFIG = {
  register: {
    mode: "form",

    // mode: "api" のとき
    apiUrl: "/api/register",

    // mode: "form" のとき
    //
    // いちばん簡単なやり方:
    //   1. Google フォームに記述式の項目を4つ作る（区分 / サロン名 / Instagram / 言語）
    //   2. 右上の「⋮」→「事前入力したURLを取得」を開く
    //   3. 4つの欄に affiliation / salon / instagram / lang とそのまま入力する
    //   4. 「リンクを取得」で出てきたURLを prefilledUrl に貼る
    //
    // 値から項目を見分けるので、entry.xxx のIDを自分で調べる必要はない。
    form: {
      prefilledUrl:
        "https://docs.google.com/forms/d/e/1FAIpQLSf31na4a91pdr8b9YRhQWKsVBIoFGNpbY9ywucFGiU2zp4tsQ/viewform" +
        "?usp=pp_url&entry.826897020=Affiliation&entry.813755346=Salon" +
        "&entry.1102650107=Instagram&entry.1127699928=Lang",

      // prefilledUrl を使わず手で指定したいときはこちら
      actionUrl: "",
      fields: {
        affiliation: "",
        salon: "",
        instagram: "",
        lang: "",
      },
    },

    // 画面に出す問い合わせ先（空なら非表示）
    contact: "",
  },
};
