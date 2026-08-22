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

    // 登録画面に出す問い合わせ先（空なら非表示）
    contact: "@driveblue_hk",
  },

  /**
   * アプリ内の「改善のご要望」欄の送信先。
   *
   * mode
   *   "form"     … Google フォームへ匿名で送る（アプリ内で完結。おすすめ）
   *   "whatsapp" … WhatsApp を開いて本人に送ってもらう（相手に電話番号が伝わる）
   *   "off"      … 欄そのものを出さない
   *
   * form のいちばん簡単なやり方:
   *   1. Google フォームに「段落」の項目を1つ作る（ご要望の本文）
   *      ＋必要なら記述式を2つ（Instagram / 言語）
   *   2. 右上の「⋮」→「事前入力したURLを取得」を開く
   *   3. 各欄に message / instagram / lang とそのまま入力する
   *   4. 「リンクを取得」で出てきたURLを prefilledUrl に貼る
   *
   * prefilledUrl が空のときは自動で WhatsApp に切り替わる。
   */
  feedback: {
    mode: "form",
    form: {
      prefilledUrl: "",

      // prefilledUrl を使わず手で指定したいときはこちら
      actionUrl: "",
      fields: {
        message: "",
        instagram: "",
        lang: "",
      },
    },
  },

  // フッターとロゴから誘導する先（空なら非表示）
  links: {
    site: "https://drivebluehk.com",
    instagram: "https://www.instagram.com/driveblue_hk/",

    // WhatsApp は「相手から送ってもらう」方式。国番号付き・記号なしの番号を入れる。
    // 電話番号をこちらから聞かずに、送ってくれた人の番号が手元に残る。
    whatsapp: "85255994111",
  },
};
