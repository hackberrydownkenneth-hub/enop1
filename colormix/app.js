/* カラー剤計算機の画面制御。計算そのものは calc.js（ColorMix）に任せる。 */
(function () {
  "use strict";

  var CM = window.ColorMix;
  var RATIOS = [1, 1.5, 2, 3];
  var TOTALS = [30, 60, 80, 100, 120, 150, 200];
  var STATE_KEY = "colormix.state.v1";
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

  var state = sanitize(readStore(STATE_KEY, null));
  if (state.items.length === 0) state.items = defaultState().items;
  var recipes = readStore(RECIPE_KEY, []) || [];
  var rows = [];

  /* ---------- 画面部品 ---------- */

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

  document.addEventListener("click", function (event) {
    var act = event.target && event.target.dataset && event.target.dataset.act;
    if (act === "ratio-minus") bumpRatio(-0.5);
    if (act === "ratio-plus") bumpRatio(0.5);
    if (act === "total-minus") bumpTotal(-10);
    if (act === "total-plus") bumpTotal(10);
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
    itemsTitle.textContent = isTotal ? "1剤のミックス" : "使う1剤の量";
    itemsHint.textContent = isTotal
      ? "まぜる1剤の「わりあい」を入れてください（例 2 : 1）。1種類だけならそのままでOK。"
      : "実際にはかる1剤のグラム数を入れてください。2剤と合計量を計算します。";
  }

  /* ---------- STEP 3: 1剤の行 ---------- */

  function renderItems() {
    var isTotal = state.mode === "total";
    itemsEl.textContent = "";
    rows = [];

    state.items.forEach(function (item, index) {
      var row = document.createElement("div");
      row.className = "item";

      var name = document.createElement("input");
      name.type = "text";
      name.className = "text-input";
      name.placeholder = "1剤 " + (index + 1) + "（例 ブラウン6）";
      name.value = item.name;
      name.setAttribute("aria-label", (index + 1) + "番目の1剤の名前");
      name.addEventListener("input", function () {
        item.name = name.value;
        update();
      });
      row.appendChild(name);

      var del = button("del-btn", "✕");
      del.setAttribute("aria-label", (index + 1) + "番目の1剤を削除");
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
      label.textContent = isTotal ? "わりあい" : "使う量";
      controls.appendChild(label);

      var minus = button("round", "−");
      var value = document.createElement("input");
      value.type = "number";
      value.className = "num-input";
      value.inputMode = "decimal";
      value.min = "0";
      value.step = isTotal ? "1" : "5";
      value.value = String(isTotal ? item.parts : item.grams);
      value.setAttribute("aria-label", (index + 1) + "番目の" + (isTotal ? "わりあい" : "使う量"));
      var plus = button("round", "＋");
      minus.setAttribute("aria-label", "減らす");
      plus.setAttribute("aria-label", "増やす");

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
    return item.name && item.name.trim() ? item.name : "1剤 " + (index + 1);
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
      err.textContent = "⚠ " + result.error;
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
        sub = "わりあい " + row.parts + "（全体の " + Math.round((row.parts / partsSum) * 100) + "%）";
      }
      resultBody.appendChild(
        resultRow(itemLabel(state.items[index], index), sub, row.text, "")
      );
    });

    if (result.items.length > 1) {
      var subtotal = document.createElement("p");
      subtotal.className = "subtotal";
      subtotal.textContent = "1剤 合計 " + CM.formatGrams(result.base1, step) + "g";
      resultBody.appendChild(subtotal);
    }

    resultBody.appendChild(
      resultRow("2剤（オキシ）", "1剤の " + result.oxRatio + " 倍", CM.formatGrams(result.ox, step), "ox")
    );
    resultBody.appendChild(
      resultRow("ぜんぶで", "", CM.formatGrams(result.total, step), "sum")
    );

    if (result.adjusted) {
      var notice = document.createElement("p");
      notice.className = "notice";
      notice.textContent =
        "※ " + result.requestedTotal + "g は " + (step < 1 ? "0.1g" : "1g") +
        " 刻みに丸めて " + CM.formatGrams(result.total, step) + "g で計算しました。";
      resultBody.appendChild(notice);
    }
  }

  function buildStepToggle() {
    var wrap = document.createElement("div");
    wrap.className = "steps-toggle";
    var label = document.createElement("span");
    label.textContent = "はかる細かさ";
    wrap.appendChild(label);

    CM.STEPS.forEach(function (step) {
      var chip = button("chip", step < 1 ? "0.1g刻み" : "1g刻み");
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
      var value = result.ok && result.items[index] ? result.items[index].text + "g" : "-";
      row.badge.textContent = value;
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
    var lines = ["【カラーレシピ】", "1剤 : 2剤 ＝ " + CM.formatRatio(result.oxRatio), ""];
    result.items.forEach(function (row, index) {
      lines.push(itemLabel(state.items[index], index) + "  " + row.text + "g");
    });
    lines.push("--------------------");
    if (result.items.length > 1) {
      lines.push("1剤 合計  " + CM.formatGrams(result.base1, step) + "g");
    }
    lines.push("2剤       " + CM.formatGrams(result.ox, step) + "g");
    lines.push("ぜんぶで  " + CM.formatGrams(result.total, step) + "g");
    return lines.join("\n");
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () {
          toast("コピーしました");
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
    toast(ok ? "コピーしました" : "コピーできませんでした");
  }

  $("copy-btn").addEventListener("click", function () {
    var text = resultText(lastResult);
    if (!text) {
      toast("先に入力してください");
      return;
    }
    copyText(text);
  });

  function recipeSummary(saved) {
    var names = saved.state.items
      .map(function (item, index) {
        return itemLabelOf(item, index);
      })
      .join(" / ");
    return CM.formatRatio(saved.state.oxRatio) + "　" + names;
  }

  function itemLabelOf(item, index) {
    return item.name && item.name.trim() ? item.name : "1剤 " + (index + 1);
  }

  $("save-btn").addEventListener("click", function () {
    var suggestion = itemLabelOf(state.items[0], 0);
    var name = window.prompt("レシピの名前をつけてください", suggestion);
    if (name === null) return;
    name = name.trim() || suggestion;
    recipes.unshift({ name: name, state: JSON.parse(JSON.stringify(state)) });
    recipes = recipes.slice(0, 30);
    writeStore(RECIPE_KEY, recipes);
    renderRecipes();
    toast("保存しました");
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
        toast("よびだしました");
      });

      var del = button("del-btn", "✕");
      del.setAttribute("aria-label", saved.name + " を削除");
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
    if (!window.confirm("入力をリセットしますか？（保存したレシピは消えません）")) return;
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
    totalInput.value = String(state.total);
    syncMode();
    syncRatio();
    syncTotal();
    syncStep();
    renderItems();
    update();
  }

  buildStepToggle();
  renderRecipes();
  syncAll();
  watchResultCard();
})();
