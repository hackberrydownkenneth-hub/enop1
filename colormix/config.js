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
    mode: "local",

    // mode: "api" のとき
    apiUrl: "/api/register",

    // mode: "form" のとき（Google フォームの送信先と entry.xxx フィールドID）
    form: {
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
