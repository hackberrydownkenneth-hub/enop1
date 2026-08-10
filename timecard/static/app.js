// ヘッダーに現在時刻を表示する
(function () {
  const el = document.getElementById("clock");
  if (!el) return;
  function tick() {
    const now = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    const days = ["日", "月", "火", "水", "木", "金", "土"];
    el.textContent =
      `${now.getFullYear()}/${pad(now.getMonth() + 1)}/${pad(now.getDate())}` +
      `(${days[now.getDay()]}) ` +
      `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  }
  tick();
  setInterval(tick, 1000);
})();
