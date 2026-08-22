/**
 * はじめて使う人だけに出す利用登録。
 *
 * ・所属（サロン / フリーランス）と Instagram を聞いてから計算機を使えるようにする
 * ・一度登録したら二度と出さない（端末の localStorage に記録）
 * ・送信先は config.js の register.mode で切り替える
 */
(function () {
  "use strict";

  var I18N = window.ColorMixI18N;
  var Profile = window.ColorMixProfile;
  var PROFILE_KEY = "colormix.profile.v1";

  var defaults = {
    mode: "local",
    apiUrl: "/api/register",
    form: { actionUrl: "", fields: {} },
    contact: "",
  };
  var config = Object.assign(
    {},
    defaults,
    (window.COLORMIX_CONFIG && window.COLORMIX_CONFIG.register) || {}
  );

  // Google フォームの「事前入力したURL」が入っていれば、そこから送信先とIDを組み立てる
  if (config.mode === "form" && config.form && config.form.prefilledUrl) {
    var parsed = Profile.parseGoogleForm(config.form.prefilledUrl);
    if (parsed) {
      config.form = Object.assign({}, config.form, parsed);
    } else if (window.console && console.warn) {
      console.warn(
        "[colormix] 事前入力URLを読み取れませんでした。各欄に affiliation / salon / instagram / lang と入れて取得しなおしてください。"
      );
    }
  }

  var t = I18N.scoped(I18N.current);

  /* ---------- 保存 ---------- */

  function readProfile() {
    try {
      var raw = localStorage.getItem(PROFILE_KEY);
      var parsed = raw ? JSON.parse(raw) : null;
      return parsed && parsed.instagram ? parsed : null;
    } catch (e) {
      return null;
    }
  }

  function writeProfile(profile) {
    try {
      localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
    } catch (e) {
      /* 保存できなくても使えるようにはする */
    }
  }

  function clearProfile() {
    try {
      localStorage.removeItem(PROFILE_KEY);
    } catch (e) {
      /* noop */
    }
  }

  /* ---------- 送信 ---------- */

  /** 送信先がちゃんと設定されているモードのときだけ「集める」と言う */
  function collects() {
    if (config.mode === "api") return Boolean(config.apiUrl);
    if (config.mode === "form") return Boolean(config.form && config.form.actionUrl);
    return false;
  }

  /** 送信できたら true。失敗しても例外は投げない */
  function send(record) {
    if (config.mode === "api") {
      return fetch(config.apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(record),
      }).then(function (response) {
        return response.ok;
      });
    }

    if (config.mode === "form" && config.form && config.form.actionUrl) {
      var body = new FormData();
      var fields = config.form.fields || {};
      Object.keys(fields).forEach(function (key) {
        if (fields[key]) body.append(fields[key], record[key] || "");
      });
      // Google フォームは CORS を返さないので結果は読めない。送れたら成功とみなす
      return fetch(config.form.actionUrl, {
        method: "POST",
        mode: "no-cors",
        body: body,
      }).then(function () {
        return true;
      });
    }

    return Promise.resolve(false);
  }

  function trySend(record) {
    if (!collects()) return Promise.resolve(false);
    return send(record).catch(function () {
      return false;
    });
  }

  /** 前回送れなかった分をこっそり送りなおす */
  function retryPending() {
    var profile = readProfile();
    if (!profile || profile.synced || !collects()) return;
    trySend(Profile.buildRecord(profile, profile)).then(function (sent) {
      if (!sent) return;
      profile.synced = true;
      writeProfile(profile);
      renderManage();
    });
  }

  /** wa.me のリンク。メッセージを入れておけるので、相手は送信するだけで済む */
  function whatsappLink(message) {
    var number = (window.COLORMIX_CONFIG &&
      window.COLORMIX_CONFIG.links &&
      window.COLORMIX_CONFIG.links.whatsapp) || "";
    if (!number) return "";
    return (
      "https://wa.me/" +
      String(number).replace(/[^0-9]/g, "") +
      "?text=" +
      encodeURIComponent(message)
    );
  }

  /* ---------- 画面の下ごしらえ ---------- */

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  var backdrop = null;
  var state = { affiliation: "", consent: false, busy: false };
  var refs = {};

  var pageParts = function () {
    return [
      document.querySelector(".header"),
      document.querySelector(".main"),
      document.getElementById("sticky-bar"),
    ].filter(Boolean);
  };

  function setPageInert(on) {
    pageParts().forEach(function (part) {
      if (on) {
        part.setAttribute("inert", "");
        part.setAttribute("aria-hidden", "true");
      } else {
        part.removeAttribute("inert");
        part.removeAttribute("aria-hidden");
      }
    });
    document.body.classList.toggle("gate-open", on);
  }

  /* ---------- 登録画面 ---------- */

  function buildGate(previous) {
    if (previous) {
      state.affiliation = previous.affiliation || "";
    }
    backdrop = el("div", "gate");
    backdrop.setAttribute("role", "dialog");
    backdrop.setAttribute("aria-modal", "true");

    var card = el("div", "gate-card");
    backdrop.appendChild(card);

    // 言語切り替え（登録画面が最初に出るので、ここにも要る）
    var langRow = el("div", "gate-lang");
    langRow.setAttribute("role", "group");
    refs.langButtons = I18N.LANGS.map(function (code) {
      var btn = el("button", "gate-lang-btn", I18N.translate(code, "lang.name"));
      btn.type = "button";
      btn.addEventListener("click", function () {
        I18N.set(code);
      });
      langRow.appendChild(btn);
      return { code: code, btn: btn };
    });
    card.appendChild(langRow);

    refs.title = el("h2", "gate-title");
    refs.title.id = "gate-title";
    backdrop.setAttribute("aria-labelledby", "gate-title");
    card.appendChild(refs.title);

    refs.lead = el("p", "gate-lead");
    card.appendChild(refs.lead);

    // 所属
    refs.q1 = el("h3", "gate-q");
    card.appendChild(refs.q1);
    var options = el("div", "gate-options");
    refs.options = Profile.AFFILIATIONS.map(function (value) {
      var btn = el("button", "gate-option");
      btn.type = "button";
      btn.setAttribute("aria-pressed", "false");
      var strong = el("strong");
      var small = el("small");
      btn.appendChild(strong);
      btn.appendChild(small);
      btn.addEventListener("click", function () {
        state.affiliation = value;
        syncOptions();
        clearError();
      });
      options.appendChild(btn);
      return { value: value, btn: btn, strong: strong, small: small };
    });
    card.appendChild(options);

    // サロン名（サロン所属のときだけ）
    refs.salonWrap = el("div", "gate-field");
    refs.salonLabel = el("label", "gate-label");
    refs.salonLabel.htmlFor = "gate-salon";
    refs.salon = el("input", "text-input");
    refs.salon.id = "gate-salon";
    refs.salon.type = "text";
    refs.salon.maxLength = Profile.SALON_MAX;
    refs.salonWrap.appendChild(refs.salonLabel);
    refs.salonWrap.appendChild(refs.salon);
    card.appendChild(refs.salonWrap);

    // Instagram
    var igWrap = el("div", "gate-field");
    refs.igLabel = el("label", "gate-label");
    refs.igLabel.htmlFor = "gate-instagram";
    refs.igHint = el("p", "gate-hint");
    var igRow = el("div", "gate-ig");
    igRow.appendChild(el("span", "gate-at", "@"));
    refs.instagram = el("input", "text-input");
    refs.instagram.id = "gate-instagram";
    refs.instagram.type = "text";
    refs.instagram.autocapitalize = "off";
    refs.instagram.autocomplete = "off";
    refs.instagram.spellcheck = false;
    refs.instagram.addEventListener("input", clearError);
    igRow.appendChild(refs.instagram);
    igWrap.appendChild(refs.igLabel);
    igWrap.appendChild(refs.igHint);
    igWrap.appendChild(igRow);
    card.appendChild(igWrap);

    // 使いみち＋同意
    refs.purpose = el("p", "gate-purpose");
    card.appendChild(refs.purpose);

    var consentRow = el("label", "gate-consent");
    refs.consent = document.createElement("input");
    refs.consent.type = "checkbox";
    refs.consent.addEventListener("change", function () {
      state.consent = refs.consent.checked;
      clearError();
    });
    refs.consentText = el("span");
    consentRow.appendChild(refs.consent);
    consentRow.appendChild(refs.consentText);
    card.appendChild(consentRow);

    refs.error = el("p", "gate-error");
    refs.error.setAttribute("role", "alert");
    refs.error.hidden = true;
    card.appendChild(refs.error);

    refs.submit = el("button", "gate-submit");
    refs.submit.type = "button";
    refs.submit.addEventListener("click", onSubmit);
    card.appendChild(refs.submit);

    refs.contact = el("p", "gate-contact");
    card.appendChild(refs.contact);

    // タブ移動をカードの中だけに閉じ込める
    backdrop.addEventListener("keydown", function (event) {
      if (event.key !== "Tab") return;
      var focusable = card.querySelectorAll(
        'button, input, [href], select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (!focusable.length) return;
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });

    if (previous) {
      refs.salon.value = previous.salon || "";
      refs.instagram.value = previous.instagram || "";
    }

    document.body.appendChild(backdrop);
    applyGateText();
    syncOptions();
    setPageInert(true);
    refs.options[0].btn.focus();
  }

  function applyGateText() {
    if (!backdrop) return;
    refs.title.textContent = t("reg.title");
    refs.lead.textContent = t("reg.lead");
    refs.q1.textContent = t("reg.q1");
    refs.options.forEach(function (option) {
      option.strong.textContent = t("reg.opt." + option.value);
      option.small.textContent = t("reg.opt." + option.value + ".sub");
    });
    refs.salonLabel.textContent = t("reg.salonName");
    refs.salon.placeholder = t("reg.salonName.ph");
    refs.igLabel.textContent = t("reg.q2");
    refs.igHint.textContent = t("reg.q2.hint");
    refs.instagram.placeholder = t("reg.instagram.ph");
    refs.instagram.setAttribute("aria-label", t("reg.q2"));
    refs.purpose.textContent = t(collects() ? "reg.purpose.collect" : "reg.purpose.local");
    refs.consentText.textContent = t("reg.consent");
    refs.submit.textContent = t(state.busy ? "reg.submitting" : "reg.submit");
    refs.contact.textContent = config.contact
      ? t("reg.contact", { contact: config.contact })
      : "";
    refs.contact.hidden = !config.contact;
    I18N.LANGS.forEach(function (code, index) {
      refs.langButtons[index].btn.setAttribute(
        "aria-pressed",
        code === I18N.current() ? "true" : "false"
      );
    });
    if (refs.error.dataset.code) {
      refs.error.textContent = t("reg.err." + refs.error.dataset.code);
    }
  }

  function syncOptions() {
    refs.options.forEach(function (option) {
      option.btn.setAttribute(
        "aria-pressed",
        option.value === state.affiliation ? "true" : "false"
      );
    });
    refs.salonWrap.hidden = state.affiliation !== "salon";
  }

  function clearError() {
    refs.error.hidden = true;
    refs.error.textContent = "";
    delete refs.error.dataset.code;
  }

  function showError(code, field) {
    refs.error.dataset.code = code;
    refs.error.textContent = t("reg.err." + code);
    refs.error.hidden = false;
    if (field && field.focus) field.focus();
  }

  function onSubmit() {
    if (state.busy) return;

    var result = Profile.validate({
      affiliation: state.affiliation,
      salon: refs.salon.value,
      instagram: refs.instagram.value,
      consent: state.consent,
    });

    if (!result.ok) {
      if (result.errors.affiliation) {
        showError(result.errors.affiliation, refs.options[0].btn);
      } else if (result.errors.salon) {
        showError(result.errors.salon, refs.salon);
      } else if (result.errors.instagram) {
        showError(result.errors.instagram, refs.instagram);
      } else {
        showError(result.errors.consent, refs.consent);
      }
      return;
    }

    state.busy = true;
    refs.submit.disabled = true;
    refs.submit.textContent = t("reg.submitting");

    var record = Profile.buildRecord(result.value, {
      lang: I18N.current(),
      registeredAt: new Date().toISOString(),
    });

    var collecting = collects();
    trySend(record).then(function (sent) {
      // collected: この登録が「集める」と伝えたうえで行われたかどうか
      var profile = Object.assign({}, record, {
        synced: sent || !collecting,
        collected: collecting,
      });
      writeProfile(profile);
      renderManage();
      if (collecting && !sent) notify(t("reg.warn.offline"));

      // WhatsApp の案内があるときだけ、閉じる前に完了画面を挟む
      var link = whatsappLink(t("reg.whatsapp.message", { instagram: record.instagram }));
      if (link) showDone(link);
      else closeGate();
    });
  }

  /**
   * 登録直後に出す完了画面。
   * こちらから電話番号を聞かず、相手から WhatsApp を送ってもらう導線にする。
   */
  function showDone(link) {
    var card = backdrop.querySelector(".gate-card");
    card.textContent = "";
    card.classList.add("gate-done");

    var check = el("p", "gate-done-mark", "✓");
    var title = el("h2", "gate-title", t("reg.done.title"));
    var lead = el("p", "gate-lead", t("reg.done.lead"));
    var note = el("p", "gate-note", t("reg.done.note"));

    var wa = document.createElement("a");
    wa.className = "gate-whatsapp";
    wa.href = link;
    wa.target = "_blank";
    wa.rel = "noopener noreferrer";
    wa.textContent = t("reg.done.whatsapp");

    var start = el("button", "gate-submit", t("reg.done.start"));
    start.type = "button";
    start.addEventListener("click", closeGate);

    card.appendChild(check);
    card.appendChild(title);
    card.appendChild(lead);
    card.appendChild(wa);
    card.appendChild(note);
    card.appendChild(start);
    start.focus();
  }

  function closeGate() {
    if (!backdrop) return;
    backdrop.remove();
    backdrop = null;
    state.busy = false;
    setPageInert(false);
  }

  /** 画面下に短く出すお知らせ（app.js のトーストと同じ見た目） */
  function notify(message) {
    var existing = document.querySelector(".toast");
    if (existing) existing.remove();
    var toast = el("div", "toast", message);
    document.body.appendChild(toast);
    setTimeout(function () {
      toast.remove();
    }, 2600);
  }

  /* ---------- 登録情報の確認・削除 ---------- */

  function renderManage() {
    var host = document.getElementById("reg-manage");
    if (!host) return;
    host.textContent = "";

    var profile = readProfile();
    if (!profile) {
      host.hidden = true;
      return;
    }
    host.hidden = false;

    var title = el("p", "manage-title", t("reg.manage.title"));
    var who = el(
      "p",
      "manage-who",
      t("reg.aff." + profile.affiliation) +
        "・@" +
        profile.instagram +
        (profile.salon ? "・" + profile.salon : "") +
        (profile.synced ? "" : t("reg.manage.pending"))
    );
    var del = el("button", "manage-del", t("reg.manage.delete"));
    del.type = "button";
    del.addEventListener("click", function () {
      clearProfile();
      renderManage();
      notify(t("reg.manage.deleted"));
    });

    host.appendChild(title);
    host.appendChild(who);
    host.appendChild(del);
  }

  /* ---------- 起動 ---------- */

  I18N.onChange(function () {
    applyGateText();
    renderManage();
  });

  /**
   * 登録画面を出すか。
   *
   * ・まだ登録していない人 … 出す
   * ・「どこにも送信しません」と伝えた状態で登録した人が、収集を有効にした
   *   あとに来た場合 … もう一度だけ出す。伝えた内容と違う扱いを黙って
   *   することはしない（前回の入力は埋めた状態にする）
   */
  function needsGate(profile) {
    if (config.mode === "off") return false;
    if (!profile) return true;
    return collects() && profile.collected !== true;
  }

  var stored = readProfile();
  if (needsGate(stored)) {
    buildGate(stored);
  } else {
    retryPending();
  }
  renderManage();

  window.ColorMixRegister = {
    getProfile: readProfile,
    clearProfile: clearProfile,
    collects: collects,
  };
})();
