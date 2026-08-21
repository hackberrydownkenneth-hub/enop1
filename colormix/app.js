/* カラー剤計算機の画面制御。計算は calc.js、文言は i18n.js に任せる。 */
(function () {
  "use strict";

  var CM = window.ColorMix;
  var I18N = window.ColorMixI18N;
  var RATIOS = [1, 1.5, 2, 3];
  var TOTALS = [30, 60, 80, 100, 120, 150, 200];
  var ADD_ONS = [5, 7, 10];
  var STATE_KEY = "colormix.state.v1";
  var ADDON_KEY = "colormix.addon.v1";
  var RECIPE_KEY = "colormix.recipes.v1";

  var $ = function (id) {
    return document.getElementById(id);
  };

  /* ---------- 保存（localStorage が使えなくても動く） ---------- */

  function readStore(key, fallback) {
    try {
      var raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) {
      return fallback;
    }
  }

  function writeStore(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
      /* プライベートモードなどでは保存しないだけ */
    }
  }

  /* ---------- 言語（状態は i18n.js が持つ。登録画面と共有する） ---------- */

  var t = I18N.scoped(I18N.current);

  /**
   * **強調** を <b> に変えながらテキストを流し込む。
   * innerHTML を使わないので、文言に記号が入っても壊れない。
   */
  function setText(el, text) {
    el.textContent = "";
    String(text)
      .split("**")
      .forEach(function (chunk, index) {
        if (!chunk) return;
        if (index % 2 === 1) {
          var strong = document.createElement("b");
          strong.textContent = chunk;
          el.appendChild(strong);
        } else {
          el.appendChild(document.createTextNode(chunk));
        }
      });
  }

  /* ---------- 状態 ---------- */

  function defaultState() {
    return {
      mode: "total",
      oxRatio: 1,
      total: 100,
      step: 1,
      items: [
        { name: "", parts: 1, grams: 30 },
        { name: "", parts: 1, grams: 30 },
      ],
    };
  }

  function sanitize(saved) {
    var base = defaultState();
    if (!saved || typeof saved !== "object") return base;
    var items = Array.isArray(saved.items) ? saved.items : base.items;
    return {
      mode: saved.mode === "base" ? "base" : "total",
      oxRatio: num(saved.oxRatio, 1),
      total: num(saved.total, 100),
      step: saved.step === 0.1 ? 0.1 : 1,
      items: items.slice(0, 12).map(function (item) {
        return {
          name: typeof item.name === "string" ? item.name.slice(0, 40) : "",
          parts: num(item.parts, 1),
          grams: num(item.grams, 30),
        };
      }),
    };
  }

  function num(value, fallback) {
    var parsed = parseFloat(value);
    return isFinite(parsed) && parsed >= 0 ? parsed : fallback;
  }

  function parseInput(value) {
    var parsed = parseFloat(value);
    return isFinite(parsed) && parsed >= 0 ? parsed : 0;
  }

  /* 追い足し計算は上の配合計算とは別枠。状態も別に持つ */
  function sanitizeAddOn(saved) {
    if (!saved || typeof saved !== "object") return { remain: 40, percent: 5 };
    return {
      remain: num(saved.remain, 40),
      percent: Math.min(num(saved.percent, 5), 100),
    };
  }

  var state = sanitize(readStore(STATE_KEY, null));
  if (state.items.length === 0) state.items = defaultState().items;
  var addOn = sanitizeAddOn(readStore(ADDON_KEY, null));
  var recipes = readStore(RECIPE_KEY, []) || [];
  var rows = [];

  /* ---------- 画面部品 ---------- */

  var langSwitch = $("lang-switch");
  var ratioChips = $("ratio-chips");
  var ratioCustom = $("ratio-custom");
  var ratioView = $("ratio-view");
  var totalCard = $("total-card");
  var totalChips = $("total-chips");
  var totalInput = $("total-input");
  var itemsEl = $("items");
  var itemsTitle = $("items-title");
  var itemsHint = $("items-hint");
  var itemsStepNo = $("items-step-no");
  var addOnRemain = $("addon-remain");
  var addOnChips = $("addon-chips");
  var addOnInput = $("addon-input");
  var addOnBody = $("addon-body");
  var resultCard = $("result-card");
  var resultBody = $("result-body");
  var recipesCard = $("recipes-card");
  var recipesEl = $("recipes");
  var stickyBar = $("sticky-bar");
  var stepToggle = null;

  function button(className, text) {
    var el = document.createElement("button");
    el.type = "button";
    el.className = className;
    el.textContent = text;
    return el;
  }

  /* ---------- 言語切り替え ---------- */

  I18N.LANGS.forEach(function (code) {
    var btn = button("lang-btn", I18N.translate(code, "lang.name"));
    btn.dataset.lang = code;
    btn.addEventListener("click", function () {
      I18N.set(code);
    });
    langSwitch.appendChild(btn);
  });

  /** 静的な文言（data-i18n / data-i18n-aria）をまとめて差し替える */
  function applyLang() {
    document.documentElement.lang = t("lang.tag");
    document.title = t("app.docTitle");

    Array.prototype.forEach.call(
      document.querySelectorAll("[data-i18n]"),
      function (el) {
        setText(el, t(el.dataset.i18n));
      }
    );
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-i18n-aria]"),
      function (el) {
        el.setAttribute("aria-label", t(el.dataset.i18nAria));
      }
    );
    Array.prototype.forEach.call(langSwitch.children, function (btn) {
      btn.setAttribute(
        "aria-pressed",
        btn.dataset.lang === I18N.current() ? "true" : "false"
      );
    });
    if (stepToggle) {
      Array.prototype.forEach.call(stepToggle.querySelectorAll(".chip"), function (chip) {
        chip.textContent = t("step." + chip.dataset.step);
      });
      setText(stepToggle.querySelector(".steps-label"), t("step.label"));
    }
  }

  /* ---------- STEP 1: 2剤のわりあい ---------- */

  RATIOS.forEach(function (ratio) {
    var chip = button("chip", "1 : " + ratio);
    chip.dataset.ratio = String(ratio);
    chip.addEventListener("click", function () {
      state.oxRatio = ratio;
      ratioCustom.value = String(ratio);
      syncRatio();
      update();
    });
    ratioChips.appendChild(chip);
  });

  ratioCustom.addEventListener("input", function () {
    state.oxRatio = parseInput(ratioCustom.value);
    syncRatio();
    update();
  });

  function bumpRatio(delta) {
    state.oxRatio = Math.max(0, Math.round((state.oxRatio + delta) * 10) / 10);
    ratioCustom.value = String(state.oxRatio);
    syncRatio();
    update();
  }

  function syncRatio() {
    Array.prototype.forEach.call(ratioChips.children, function (chip) {
      chip.setAttribute(
        "aria-pressed",
        Number(chip.dataset.ratio) === state.oxRatio ? "true" : "false"
      );
    });
    ratioView.textContent = CM.formatRatio(state.oxRatio);
  }

  /* ---------- STEP 2: 合計量 ---------- */

  TOTALS.forEach(function (total) {
    var chip = button("chip", total + "g");
    chip.dataset.total = String(total);
    chip.addEventListener("click", function () {
      state.total = total;
      totalInput.value = String(total);
      syncTotal();
      update();
    });
    totalChips.appendChild(chip);
  });

  totalInput.addEventListener("input", function () {
    state.total = parseInput(totalInput.value);
    syncTotal();
    update();
  });

  function bumpTotal(delta) {
    state.total = Math.max(0, Math.round((state.total + delta) * 10) / 10);
    totalInput.value = String(state.total);
    syncTotal();
    update();
  }

  function syncTotal() {
    Array.prototype.forEach.call(totalChips.children, function (chip) {
      chip.setAttribute(
        "aria-pressed",
        Number(chip.dataset.total) === state.total ? "true" : "false"
      );
    });
  }

  /* ---------- 追い足し計算（上の計算とは別枠） ---------- */

  ADD_ONS.forEach(function (percent) {
    var chip = button("chip", percent + "%");
    chip.dataset.addon = String(percent);
    chip.addEventListener("click", function () {
      addOn.percent = percent;
      addOnInput.value = String(percent);
      updateAddOn();
    });
    addOnChips.appendChild(chip);
  });

  addOnRemain.addEventListener("input", function () {
    addOn.remain = parseInput(addOnRemain.value);
    updateAddOn();
  });

  addOnInput.addEventListener("input", function () {
    addOn.percent = Math.min(parseInput(addOnInput.value), 100);
    updateAddOn();
  });

  function bumpRemain(delta) {
    addOn.remain = Math.max(0, Math.round((addOn.remain + delta) * 10) / 10);
    addOnRemain.value = String(addOn.remain);
    updateAddOn();
  }

  function bumpAddOn(delta) {
    addOn.percent = Math.min(
      100,
      Math.max(0, Math.round((addOn.percent + delta) * 10) / 10)
    );
    addOnInput.value = String(addOn.percent);
    updateAddOn();
  }

  function renderAddOn(result) {
    addOnBody.textContent = "";

    if (!result.ok) {
      var err = document.createElement("p");
      err.className = "error";
      err.textContent = "⚠ " + t("err." + result.code);
      addOnBody.appendChild(err);
      return;
    }

    addOnBody.appendChild(
      resultRow(
        t("addon.result"),
        t("addon.resultSub", { remain: result.remainText, pct: result.percent }),
        result.text,
        "addon"
      )
    );

    var after = document.createElement("p");
    after.className = "addon-after";
    after.textContent = t("addon.after", { g: result.totalText });
    addOnBody.appendChild(after);
  }

  /** 追い足しだけを計算し直す（配合計算には触らない） */
  function updateAddOn() {
    Array.prototype.forEach.call(addOnChips.children, function (chip) {
      chip.setAttribute(
        "aria-pressed",
        Number(chip.dataset.addon) === addOn.percent ? "true" : "false"
      );
    });
    renderAddOn(
      CM.calcAddOn({
        remain: addOn.remain,
        percent: addOn.percent,
        step: state.step,
      })
    );
    writeStore(ADDON_KEY, addOn);
  }

  document.addEventListener("click", function (event) {
    var act = event.target && event.target.dataset && event.target.dataset.act;
    if (act === "ratio-minus") bumpRatio(-0.5);
    if (act === "ratio-plus") bumpRatio(0.5);
    if (act === "total-minus") bumpTotal(-10);
    if (act === "total-plus") bumpTotal(10);
    if (act === "addon-minus") bumpAddOn(-1);
    if (act === "addon-plus") bumpAddOn(1);
    if (act === "remain-minus") bumpRemain(-10);
    if (act === "remain-plus") bumpRemain(10);
  });

  /* ---------- モード切り替え ---------- */

  Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (tab) {
    tab.addEventListener("click", function () {
      state.mode = tab.dataset.mode;
      syncMode();
      renderItems();
      update();
    });
  });

  function syncMode() {
    var isTotal = state.mode === "total";
    Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (tab) {
      tab.setAttribute("aria-selected", tab.dataset.mode === state.mode ? "true" : "false");
    });
    totalCard.hidden = !isTotal;
    itemsStepNo.textContent = isTotal ? "3" : "2";
    itemsTitle.textContent = t(isTotal ? "items.title.total" : "items.title.base");
    itemsHint.textContent = t(isTotal ? "items.hint.total" : "items.hint.base");
  }

  /* ---------- STEP 3: 1剤の行 ---------- */

  function renderItems() {
    var isTotal = state.mode === "total";
    var valueLabel = t(isTotal ? "label.parts" : "label.grams");
    itemsEl.textContent = "";
    rows = [];

    state.items.forEach(function (item, index) {
      var no = index + 1;
      var row = document.createElement("div");
      row.className = "item";

      var name = document.createElement("input");
      name.type = "text";
      name.className = "text-input";
      name.placeholder = t("item.placeholder", { n: no });
      name.value = item.name;
      name.setAttribute("aria-label", t("item.aria.name", { n: no }));
      name.addEventListener("input", function () {
        item.name = name.value;
        update();
      });
      row.appendChild(name);

      var del = button("del-btn", "✕");
      del.setAttribute("aria-label", t("item.aria.del", { n: no }));
      del.disabled = state.items.length <= 1;
      del.addEventListener("click", function () {
        if (state.items.length <= 1) return;
        state.items.splice(index, 1);
        renderItems();
        update();
      });
      row.appendChild(del);

      var controls = document.createElement("div");
      controls.className = "item-controls";

      var label = document.createElement("span");
      label.className = "label";
      label.textContent = valueLabel;
      controls.appendChild(label);

      var minus = button("round", "−");
      var value = document.createElement("input");
      value.type = "number";
      value.className = "num-input";
      value.inputMode = "decimal";
      value.min = "0";
      value.step = isTotal ? "1" : "5";
      value.value = String(isTotal ? item.parts : item.grams);
      value.setAttribute("aria-label", t("item.aria.value", { n: no, label: valueLabel }));
      var plus = button("round", "＋");
      minus.setAttribute("aria-label", t("item.aria.minus"));
      plus.setAttribute("aria-label", t("item.aria.plus"));

      var stepSize = isTotal ? 1 : 5;
      function setValue(next) {
        var fixed = Math.max(0, Math.round(next * 10) / 10);
        if (isTotal) item.parts = fixed;
        else item.grams = fixed;
        value.value = String(fixed);
        update();
      }
      minus.addEventListener("click", function () {
        setValue((isTotal ? item.parts : item.grams) - stepSize);
      });
      plus.addEventListener("click", function () {
        setValue((isTotal ? item.parts : item.grams) + stepSize);
      });
      value.addEventListener("input", function () {
        var parsed = parseInput(value.value);
        if (isTotal) item.parts = parsed;
        else item.grams = parsed;
        update();
      });

      controls.appendChild(minus);
      controls.appendChild(value);
      controls.appendChild(plus);

      if (!isTotal) {
        var unit = document.createElement("span");
        unit.className = "unit";
        unit.textContent = "g";
        controls.appendChild(unit);
      }

      var badge = document.createElement("span");
      badge.className = "item-badge";
      badge.textContent = "-";
      if (!isTotal) badge.style.display = "none";
      controls.appendChild(badge);

      row.appendChild(controls);
      itemsEl.appendChild(row);
      rows.push({ badge: badge });
    });
  }

  $("add-item").addEventListener("click", function () {
    if (state.items.length >= 12) return;
    state.items.push({ name: "", parts: 1, grams: 10 });
    renderItems();
    update();
  });

  /* ---------- 結果 ---------- */

  function itemLabel(item, index) {
    return item && item.name && item.name.trim()
      ? item.name
      : t("item.fallback", { n: index + 1 });
  }

  function resultRow(name, sub, grams, className) {
    var row = document.createElement("div");
    row.className = "rrow" + (className ? " " + className : "");

    var left = document.createElement("div");
    left.className = "rname";
    left.appendChild(document.createTextNode(name));
    if (sub) {
      var small = document.createElement("small");
      small.textContent = sub;
      left.appendChild(small);
    }

    var right = document.createElement("div");
    right.className = "rgram";
    right.appendChild(document.createTextNode(grams));
    var unit = document.createElement("span");
    unit.textContent = "g";
    right.appendChild(unit);

    row.appendChild(left);
    row.appendChild(right);
    return row;
  }

  function renderResult(result) {
    resultBody.textContent = "";

    if (!result.ok) {
      var err = document.createElement("p");
      err.className = "error";
      err.textContent = "⚠ " + t("err." + result.code);
      resultBody.appendChild(err);
      return;
    }

    var step = result.step;
    var partsSum = result.items.reduce(function (a, row) {
      return a + row.parts;
    }, 0);

    result.items.forEach(function (row, index) {
      var sub = "";
      if (state.mode === "total" && result.items.length > 1 && partsSum > 0) {
        sub = t("result.partsSub", {
          parts: row.parts,
          pct: Math.round((row.parts / partsSum) * 100),
        });
      }
      resultBody.appendChild(
        resultRow(itemLabel(state.items[index], index), sub, row.text, "")
      );
    });

    if (result.items.length > 1) {
      var subtotal = document.createElement("p");
      subtotal.className = "subtotal";
      subtotal.textContent = t("result.subtotal", {
        g: CM.formatGrams(result.base1, step),
      });
      resultBody.appendChild(subtotal);
    }

    resultBody.appendChild(
      resultRow(
        t("result.ox"),
        t("result.oxSub", { r: result.oxRatio }),
        CM.formatGrams(result.ox, step),
        "ox"
      )
    );
    resultBody.appendChild(
      resultRow(t("result.sum"), "", CM.formatGrams(result.total, step), "sum")
    );

    if (result.adjusted) {
      var notice = document.createElement("p");
      notice.className = "notice";
      notice.textContent = t("result.notice", {
        req: result.requestedTotal,
        step: step < 1 ? "0.1g" : "1g",
        got: CM.formatGrams(result.total, step),
      });
      resultBody.appendChild(notice);
    }
  }

  function buildStepToggle() {
    var wrap = document.createElement("div");
    wrap.className = "steps-toggle";
    var label = document.createElement("span");
    label.className = "steps-label";
    wrap.appendChild(label);

    CM.STEPS.forEach(function (step) {
      var chip = button("chip", "");
      chip.dataset.step = String(step);
      chip.addEventListener("click", function () {
        state.step = step;
        syncStep();
        update();
      });
      wrap.appendChild(chip);
    });

    resultCard.appendChild(wrap);
    stepToggle = wrap;
  }

  function syncStep() {
    if (!stepToggle) return;
    Array.prototype.forEach.call(stepToggle.querySelectorAll(".chip"), function (chip) {
      chip.setAttribute(
        "aria-pressed",
        Number(chip.dataset.step) === state.step ? "true" : "false"
      );
    });
  }

  function renderBadges(result) {
    rows.forEach(function (row, index) {
      if (state.mode !== "total") return;
      // 結果カードの行と同じ数字にする（追い足し分は結果カード側で別に出す）
      var item = result.ok && result.items[index];
      row.badge.textContent = item ? item.text + "g" : "-";
    });
  }

  function renderSticky(result) {
    if (!result.ok) {
      stickyBar.hidden = true;
      return;
    }
    stickyBar.hidden = resultVisible;
    var step = result.step;
    $("sticky-base").textContent = CM.formatGrams(result.base1, step) + "g";
    $("sticky-ox").textContent = CM.formatGrams(result.ox, step) + "g";
    $("sticky-total").textContent = CM.formatGrams(result.total, step) + "g";
  }

  /* 結果カードが画面から外れているときだけ下部バーを出す */
  var resultVisible = true;

  function watchResultCard() {
    if (!("IntersectionObserver" in window)) return;
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          resultVisible = entry.isIntersecting;
          stickyBar.hidden = resultVisible || !lastResult.ok;
        });
      },
      { threshold: 0.25 }
    );
    observer.observe(resultCard);
  }

  /* ---------- コピー・保存・リセット ---------- */

  function resultText(result) {
    if (!result.ok) return "";
    var step = result.step;
    var lines = [t("copy.header"), t("copy.ratio") + CM.formatRatio(result.oxRatio), ""];
    result.items.forEach(function (row, index) {
      lines.push(itemLabel(state.items[index], index) + "  " + row.text + "g");
    });
    lines.push("--------------------");
    if (result.items.length > 1) {
      lines.push(t("copy.subtotal") + "  " + CM.formatGrams(result.base1, step) + "g");
    }
    lines.push(t("copy.ox") + "  " + CM.formatGrams(result.ox, step) + "g");
    lines.push(t("copy.total") + "  " + CM.formatGrams(result.total, step) + "g");
    return lines.join("\n");
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () {
          toast(t("toast.copied"));
        },
        function () {
          fallbackCopy(text);
        }
      );
    } else {
      fallbackCopy(text);
    }
  }

  function fallbackCopy(text) {
    var area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    var ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (e) {
      ok = false;
    }
    document.body.removeChild(area);
    toast(t(ok ? "toast.copied" : "toast.copy_failed"));
  }

  $("copy-btn").addEventListener("click", function () {
    var text = resultText(lastResult);
    if (!text) {
      toast(t("toast.need_input"));
      return;
    }
    copyText(text);
  });

  function recipeSummary(saved) {
    var names = saved.state.items
      .map(function (item, index) {
        return itemLabel(item, index);
      })
      .join(" / ");
    return CM.formatRatio(saved.state.oxRatio) + "　" + names;
  }

  $("save-btn").addEventListener("click", function () {
    var suggestion = itemLabel(state.items[0], 0);
    var name = window.prompt(t("prompt.save"), suggestion);
    if (name === null) return;
    name = name.trim() || suggestion;

    // 同じ名前がすでにあれば、確認のうえ置き換える（同名が並ばないように）
    var existing = -1;
    for (var i = 0; i < recipes.length; i++) {
      if (recipes[i].name === name) {
        existing = i;
        break;
      }
    }
    if (existing >= 0) {
      if (!window.confirm(t("confirm.overwrite", { name: name }))) return;
      recipes.splice(existing, 1);
    }

    recipes.unshift({ name: name, state: JSON.parse(JSON.stringify(state)) });
    recipes = recipes.slice(0, 30);
    writeStore(RECIPE_KEY, recipes);
    renderRecipes();
    toast(t("toast.saved"));
  });

  function renderRecipes() {
    recipesEl.textContent = "";
    recipesCard.hidden = recipes.length === 0;

    recipes.forEach(function (saved, index) {
      var row = document.createElement("div");
      row.className = "recipe";

      var load = button("recipe-load", "");
      load.appendChild(document.createTextNode(saved.name));
      var small = document.createElement("small");
      small.textContent = recipeSummary(saved);
      load.appendChild(small);
      load.addEventListener("click", function () {
        state = sanitize(saved.state);
        syncAll();
        toast(t("toast.loaded"));
      });

      var del = button("del-btn", "✕");
      del.setAttribute("aria-label", t("recipe.aria.del", { name: saved.name }));
      del.addEventListener("click", function () {
        recipes.splice(index, 1);
        writeStore(RECIPE_KEY, recipes);
        renderRecipes();
      });

      row.appendChild(load);
      row.appendChild(del);
      recipesEl.appendChild(row);
    });
  }

  $("reset-btn").addEventListener("click", function () {
    if (!window.confirm(t("confirm.reset"))) return;
    state = defaultState();
    syncAll();
  });

  var toastTimer = null;
  function toast(message) {
    var existing = document.querySelector(".toast");
    if (existing) existing.remove();
    var el = document.createElement("div");
    el.className = "toast";
    el.textContent = message;
    document.body.appendChild(el);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      el.remove();
    }, 1800);
  }

  /** 公式サイト・Instagram への導線（config.js の links を設定したときだけ出す） */
  function renderLinks() {
    var config = (window.COLORMIX_CONFIG && window.COLORMIX_CONFIG.links) || {};
    var host = $("footer-links");
    var lead = $("footer-lead");
    if (!host) return;

    host.textContent = "";
    var whatsapp = config.whatsapp
      ? "https://wa.me/" +
        String(config.whatsapp).replace(/[^0-9]/g, "") +
        "?text=" +
        encodeURIComponent(t("footer.whatsapp.message"))
      : "";

    var defined = [
      { key: "site", url: config.site },
      { key: "instagram", url: config.instagram },
      { key: "whatsapp", url: whatsapp },
    ].filter(function (item) {
      return item.url;
    });

    if (lead) lead.hidden = defined.length === 0;

    defined.forEach(function (item) {
      var link = document.createElement("a");
      link.className = "footer-link";
      link.href = item.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = t("footer." + item.key);
      link.setAttribute("aria-label", t("footer.aria." + item.key));
      host.appendChild(link);
    });

    // ヘッダーのロゴからも公式サイトへ行けるようにする
    var brand = $("brand-link");
    if (brand) {
      if (config.site) {
        brand.href = config.site;
        brand.target = "_blank";
        brand.rel = "noopener noreferrer";
        brand.setAttribute("aria-label", "DRIVE BLUE HONG KONG");
      } else {
        brand.removeAttribute("href");
      }
    }
  }

  /* ---------- 更新 ---------- */

  var lastResult = { ok: false };

  function update() {
    lastResult = CM.calc(state);
    renderResult(lastResult);
    renderBadges(lastResult);
    renderSticky(lastResult);
    writeStore(STATE_KEY, state);
  }

  function syncAll() {
    ratioCustom.value = String(state.oxRatio);
    addOnRemain.value = String(addOn.remain);
    addOnInput.value = String(addOn.percent);
    totalInput.value = String(state.total);
    syncMode();
    syncRatio();
    syncTotal();
    syncStep();
    renderItems();
    renderRecipes();
    update();
    updateAddOn();
  }

  I18N.onChange(function () {
    applyLang();
    renderLinks();
    syncAll();
  });

  buildStepToggle();
  applyLang();
  renderLinks();
  syncAll();
  watchResultCard();
})();
