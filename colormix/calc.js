/**
 * ヘアカラー剤の配合計算ロジック（画面から独立した純粋関数）。
 *
 * ブラウザ: script タグで読み込むと window.ColorMix から参照できる
 * Node    : require("./calc.js")
 *
 * 用語
 *   1剤   … カラー剤本体。複数種類をミックスすることがある
 *   2剤   … オキシ（過酸化水素水）。1剤の合計に対して 1:1 / 1:2 / 1:3 などで混ぜる
 *   刻み  … 秤の最小単位（1g または 0.1g）
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.ColorMix = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  /** 使用できる秤の刻み（g） */
  var STEPS = [1, 0.1];

  /** グラム → 刻み単位の整数。以降の計算は整数で行い、誤差を出さない。 */
  function toUnits(grams, step) {
    return Math.round(grams / step + 1e-9);
  }

  /** 刻み単位の整数 → グラム */
  function toGrams(units, step) {
    return Number((units * step).toFixed(3));
  }

  /** 表示用の文字列（1g 刻みなら整数、0.1g 刻みなら小数第1位） */
  function formatGrams(grams, step) {
    return step < 1 ? grams.toFixed(1) : String(Math.round(grams));
  }

  function isPositiveNumber(value) {
    return typeof value === "number" && isFinite(value) && value > 0;
  }

  function normalizeStep(step) {
    return STEPS.indexOf(step) >= 0 ? step : 1;
  }

  /**
   * total（刻み単位の整数）を parts の比率で配分する。
   * 端数は最大剰余方式で割り振るので、戻り値の合計は必ず total と一致する。
   */
  function distribute(total, parts) {
    var sum = parts.reduce(function (a, b) {
      return a + b;
    }, 0);
    if (!(sum > 0) || total <= 0) {
      return parts.map(function () {
        return 0;
      });
    }

    var allocated = [];
    var remainders = [];
    var used = 0;

    parts.forEach(function (part, index) {
      var exact = (total * part) / sum;
      var floored = Math.floor(exact + 1e-9);
      allocated.push(floored);
      used += floored;
      remainders.push({ index: index, frac: exact - floored, part: part });
    });

    // 端数が大きい順（同点なら配合比が大きい順 → 入力順）に 1 刻みずつ配る
    remainders.sort(function (a, b) {
      if (b.frac !== a.frac) return b.frac - a.frac;
      if (b.part !== a.part) return b.part - a.part;
      return a.index - b.index;
    });

    var left = total - used;
    for (var i = 0; i < left && i < remainders.length; i++) {
      allocated[remainders[i].index] += 1;
    }
    return allocated;
  }

  /** エラーはコードだけ返し、文言は画面側（i18n）に任せる */
  function error(code) {
    return { ok: false, code: code };
  }

  /**
   * 【合計量モード】1剤+2剤の合計量から、1剤それぞれと2剤のグラム数を出す。
   *
   * @param {object} input
   * @param {number} input.total    つくりたい合計量（g）
   * @param {number} input.oxRatio  1剤に対する2剤の倍率（1:2 なら 2）
   * @param {Array}  input.items    [{ name, parts }] 1剤の配合比
   * @param {number} [input.step]   秤の刻み（1 or 0.1）
   */
  function calcFromTotal(input) {
    var step = normalizeStep(input && input.step);
    var total = input ? Number(input.total) : NaN;
    var oxRatio = input ? Number(input.oxRatio) : NaN;
    var items = (input && input.items) || [];

    if (!isPositiveNumber(total)) {
      return error("need_total");
    }
    if (!(typeof oxRatio === "number" && isFinite(oxRatio) && oxRatio >= 0)) {
      return error("need_ratio");
    }
    if (items.length === 0) {
      return error("need_item");
    }

    var parts = items.map(function (item) {
      var value = Number(item.parts);
      return isFinite(value) && value > 0 ? value : 0;
    });
    var partsSum = parts.reduce(function (a, b) {
      return a + b;
    }, 0);
    if (!(partsSum > 0)) {
      return error("need_parts");
    }

    var totalUnits = toUnits(total, step);
    if (totalUnits <= 0) {
      return error("total_too_small");
    }

    // 合計量を最優先。1剤を四捨五入し、残り全部を2剤にすることで合計は必ずぴったりになる
    var base1Units = Math.round(totalUnits / (1 + oxRatio));
    var oxUnits = totalUnits - base1Units;
    if (base1Units <= 0) {
      return error("base_too_small");
    }

    var allocated = distribute(base1Units, parts);

    return buildResult({
      mode: "total",
      step: step,
      oxRatio: oxRatio,
      requestedTotal: total,
      totalUnits: totalUnits,
      base1Units: base1Units,
      oxUnits: oxUnits,
      items: items,
      parts: parts,
      allocated: allocated,
    });
  }

  /**
   * 【1剤量モード】使う1剤のグラム数から、2剤と合計量を出す。
   *
   * @param {object} input
   * @param {number} input.oxRatio  1剤に対する2剤の倍率
   * @param {Array}  input.items    [{ name, grams }] 実際に使う1剤の量
   * @param {number} [input.step]   秤の刻み（1 or 0.1）
   */
  function calcFromBase(input) {
    var step = normalizeStep(input && input.step);
    var oxRatio = input ? Number(input.oxRatio) : NaN;
    var items = (input && input.items) || [];

    if (!(typeof oxRatio === "number" && isFinite(oxRatio) && oxRatio >= 0)) {
      return error("need_ratio");
    }
    if (items.length === 0) {
      return error("need_item");
    }

    var allocated = items.map(function (item) {
      var grams = Number(item.grams);
      return isFinite(grams) && grams > 0 ? toUnits(grams, step) : 0;
    });
    var base1Units = allocated.reduce(function (a, b) {
      return a + b;
    }, 0);
    if (base1Units <= 0) {
      return error("need_grams");
    }

    var oxUnits = Math.round(base1Units * oxRatio);

    return buildResult({
      mode: "base",
      step: step,
      oxRatio: oxRatio,
      requestedTotal: null,
      totalUnits: base1Units + oxUnits,
      base1Units: base1Units,
      oxUnits: oxUnits,
      items: items,
      parts: allocated.slice(),
      allocated: allocated,
    });
  }

  function buildResult(ctx) {
    var step = ctx.step;
    var total = toGrams(ctx.totalUnits, step);
    var rows = ctx.items.map(function (item, index) {
      var grams = toGrams(ctx.allocated[index], step);
      return {
        name: (item && item.name) || "",
        parts: ctx.parts[index],
        grams: grams,
        text: formatGrams(grams, step),
      };
    });

    return {
      ok: true,
      mode: ctx.mode,
      step: step,
      oxRatio: ctx.oxRatio,
      requestedTotal: ctx.requestedTotal,
      // 入力した合計量が刻みで丸められたときだけ true
      adjusted:
        ctx.requestedTotal !== null &&
        Math.abs(ctx.requestedTotal - total) > 1e-9,
      total: total,
      base1: toGrams(ctx.base1Units, step),
      ox: toGrams(ctx.oxUnits, step),
      items: rows,
    };
  }

  /** state.mode に応じて計算を振り分ける */
  function calc(state) {
    return state && state.mode === "base"
      ? calcFromBase(state)
      : calcFromTotal(state);
  }

  /** 「1 : 2」のような比率表示 */
  function formatRatio(oxRatio) {
    var value = Number(oxRatio);
    if (!isFinite(value)) return "-";
    var text = Number.isInteger(value) ? String(value) : String(value);
    return "1 : " + text;
  }

  return {
    STEPS: STEPS,
    calc: calc,
    calcFromTotal: calcFromTotal,
    calcFromBase: calcFromBase,
    distribute: distribute,
    formatGrams: formatGrams,
    formatRatio: formatRatio,
    toUnits: toUnits,
    toGrams: toGrams,
  };
});
