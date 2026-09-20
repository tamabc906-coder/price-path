/* Price Path — giao diện tĩnh đọc docs/data/*.json do job sau phiên ghi. JS thuần, SVG string, không thư viện.
   Khung (tải dữ liệu, tab, push, toast) chép từ candle-radar/docs/app.js; phần vẽ nón viết mới. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const CFG = window.PP_CONFIG || {};
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const dmy = (iso) => (iso ? iso.slice(0, 10).split("-").reverse().slice(0, 2).join("/") : "—");
  const px = (v) => (v == null ? "—" : Number(v).toFixed(2));
  const p1 = (v) => (v == null ? "—" : Number(v).toFixed(1));
  const pct = (v) => (v == null ? "—" : Math.round(v * 100) + " %");
  const HS = ["5", "10", "20"];
  const HORIZON = 20;
  const INK = "#1F3A2E", UP = "#2E7D4F", DOWN = "#B84A3A", GOLD = "#E3B54D", GOLD2 = "#8A6A1E", MUTE = "#4B5A52", LINE = "#D9D3C3", GOLDC = "#C99A2E";
  const COVER_LO = 0.74, COVER_HI = 0.86;

  let D = null;          // latest.json
  let B = null;          // bars.json
  let cur = null;        // mã đang xem ở tab Biểu đồ
  let sortKey = "p10";
  let showScen = true;
  try { sortKey = localStorage.getItem("pp_sort") || "p10"; showScen = localStorage.getItem("pp_scen") !== "0"; } catch (_) {}

  // ---------------------------------------------------------------- chip màu theo nội dung
  function chipClass(t) {
    if (/ST xanh|dồn phiên tăng/.test(t)) return "g";
    if (/ST đỏ|dồn phiên giảm/.test(t)) return "r";
    if (/biến động cao/.test(t)) return "p";
    if (/bất thường|trần/.test(t)) return "y";
    if (/gap/.test(t)) return "b";
    return "";
  }
  const chips = (it) => (it.chips || []).map((c) => `<span class="chip ${chipClass(c)}">${esc(c)}</span>`).join("")
    + (it.level > 0 ? `<span class="chip lv">gộp cấp ${it.level}</span>` : "");
  const chgHtml = (c) => (c == null ? "" : `<span class="chg ${c > 0 ? "up" : c < 0 ? "down" : "flat"}">${c > 0 ? "▲" : c < 0 ? "▼" : "•"} ${Math.abs(c).toFixed(1)} %</span>`);

  // ---------------------------------------------------------------- nón SVG
  // bars: [[d,o,h,l,c,v], …] n phiên cuối; q: {"5":{"5":giá,…},…}; scen: [{name,weight,path[20]}]
  function coneChart(bars, q, scen, price0, W, H, opts) {
    opts = opts || {};
    const withVol = !!opts.volume, n = bars.length;
    const O = 1, HI = 2, LO = 3, C = 4, V = 5;
    // giá tại mốc t (0..20) cho phân vị qk: nội suy tuyến tính qua 0/5/10/20
    const anchors = [0, 5, 10, 20];
    const at = (qk, t) => {
      const vals = [price0, q["5"][qk], q["10"][qk], q["20"][qk]];
      for (let i = 1; i < anchors.length; i++) {
        if (t <= anchors[i]) { const a = anchors[i - 1], b = anchors[i]; return vals[i - 1] + (vals[i] - vals[i - 1]) * (t - a) / (b - a); }
      }
      return vals[3];
    };
    let lo = Math.min(...bars.map((b) => b[LO]), q["20"]["5"]);
    let hi = Math.max(...bars.map((b) => b[HI]), q["20"]["95"]);
    if (scen && showScen) scen.forEach((s) => s.path.forEach((p) => { lo = Math.min(lo, p); hi = Math.max(hi, p); }));
    const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
    const top = 6, bot = H - (withVol ? 46 : 16);
    const y = (p) => bot - (p - lo) / (hi - lo) * (bot - top);
    const leftW = W * 0.56, cw = leftW / n;
    const xc = (i) => 4 + i * cw + cw / 2;
    const xLast = xc(n - 1), rightW = W - xLast - 6;
    const xt = (t) => xLast + t / HORIZON * rightW;
    const f1 = (v) => v.toFixed(1);
    const out = [`<rect x="0" y="0" width="${W}" height="${H}" fill="#fff"/>`];
    for (let k = 1; k <= 3; k++) {
      const p = lo + (hi - lo) * k / 4;
      out.push(`<line x1="4" y1="${f1(y(p))}" x2="${W - 4}" y2="${f1(y(p))}" stroke="${LINE}" stroke-width="0.6"/>`);
      out.push(`<text x="${W - 6}" y="${f1(y(p) - 2)}" font-size="8" fill="${MUTE}" text-anchor="end" font-family="Archivo,Arial">${p1(p)}</text>`);
    }
    const bands = [["5", "95", 0.10], ["10", "90", 0.20], ["25", "75", 0.35]];
    for (const [lq, hq, op] of bands) {
      const up = [], dn = [];
      for (let t = 0; t <= HORIZON; t++) { up.push(`${f1(xt(t))},${f1(y(at(hq, t)))}`); dn.unshift(`${f1(xt(t))},${f1(y(at(lq, t)))}`); }
      out.push(`<polygon points="${up.concat(dn).join(" ")}" fill="${INK}" fill-opacity="${op}"/>`);
    }
    if (scen && showScen) {
      scen.forEach((s, i) => {
        const col = i === 0 ? GOLD : GOLD2, dash = i === 0 ? "" : ` stroke-dasharray="5 3"`;
        const pts = [`${f1(xt(0))},${f1(y(price0))}`].concat(s.path.map((p, k) => `${f1(xt(k + 1))},${f1(y(p))}`));
        out.push(`<polyline points="${pts.join(" ")}" fill="none" stroke="${col}" stroke-width="${i === 0 ? 2.2 : 1.6}" stroke-linejoin="round"${dash}/>`);
        const ey = y(s.path[s.path.length - 1]);
        out.push(`<rect x="${f1(xt(HORIZON) - 42)}" y="${f1(ey - 8)}" width="40" height="14" rx="3" fill="#fff" fill-opacity="0.9"/>`);
        out.push(`<text x="${f1(xt(HORIZON) - 22)}" y="${f1(ey + 3)}" font-size="9" font-weight="700" fill="${col}" text-anchor="middle" font-family="Archivo,Arial">${s.name} · ${Math.round(s.weight * 100)} %</text>`);
      });
    }
    const med = []; for (let t = 0; t <= HORIZON; t++) med.push(`${f1(xt(t))},${f1(y(at("50", t)))}`);
    out.push(`<polyline points="${med.join(" ")}" fill="none" stroke="${INK}" stroke-width="1.2" stroke-dasharray="3 2"/>`);
    const bw = Math.max(2, cw * 0.6);
    bars.forEach((b, i) => {
      const col = b[C] >= b[O] ? UP : DOWN, x = xc(i), yo = y(b[O]), yc = y(b[C]);
      out.push(`<line x1="${f1(x)}" y1="${f1(y(b[HI]))}" x2="${f1(x)}" y2="${f1(y(b[LO]))}" stroke="${col}" stroke-width="1"/>`);
      out.push(`<rect x="${f1(x - bw / 2)}" y="${f1(Math.min(yo, yc))}" width="${f1(bw)}" height="${f1(Math.max(1, Math.abs(yo - yc)))}" fill="${col}"/>`);
    });
    if (withVol) {
      const vols = bars.map((b) => b[V]);
      const avg = (i) => { const s = vols.slice(Math.max(0, i - 19), i + 1); return s.reduce((a, v) => a + v, 0) / s.length; };
      const ratio = vols.map((v, i) => (avg(i) ? v / avg(i) : 0));
      const vmax = Math.max(...ratio, 1), vb = H - 14, vt = H - 42;
      out.push(`<line x1="4" y1="${vb}" x2="${f1(xLast + 2)}" y2="${vb}" stroke="${LINE}" stroke-width="0.6"/>`);
      ratio.forEach((r, i) => {
        const x = xc(i), hgt = (vb - vt) * r / vmax, col = r >= 2 ? GOLDC : bars[i][C] >= bars[i][O] ? UP : DOWN;
        out.push(`<rect x="${f1(x - bw / 2)}" y="${f1(vb - hgt)}" width="${f1(bw)}" height="${f1(hgt)}" fill="${col}" fill-opacity="0.55"/>`);
      });
      out.push(`<text x="6" y="${vt + 7}" font-size="8" fill="${MUTE}" font-family="Archivo,Arial">KL / TB20</text>`);
      out.push(`<text x="${f1(xLast)}" y="${vt + 7}" font-size="8" fill="${GOLDC}" text-anchor="end" font-family="Archivo,Arial">${ratio[n - 1].toFixed(1)}×</text>`);
    }
    out.push(`<line x1="${f1(xLast)}" y1="${top}" x2="${f1(xLast)}" y2="${bot}" stroke="${GOLDC}" stroke-width="1" stroke-dasharray="2 2"/>`);
    [[5, "+5"], [10, "+10"], [20, "+20"]].forEach(([t, lab]) => out.push(`<text x="${f1(xt(t))}" y="${H - 4}" font-size="8" fill="${MUTE}" text-anchor="middle" font-family="Archivo,Arial">${lab}</text>`));
    out.push(`<text x="${f1(xLast)}" y="${H - 4}" font-size="8" fill="${GOLDC}" text-anchor="middle" font-family="Archivo,Arial">nay</text>`);
    return `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Nón xác suất">${out.join("")}</svg>`;
  }

  // ---------------------------------------------------------------- tải dữ liệu
  async function load() {
    try {
      const [r1, r2] = await Promise.all([fetch("data/latest.json", { cache: "no-cache" }), fetch("data/bars.json", { cache: "no-cache" })]);
      if (!r1.ok) throw new Error("Chưa có data/latest.json — job sau phiên chưa chạy lần nào.");
      D = await r1.json();
      B = r2.ok ? await r2.json() : { bars: {} };
    } catch (err) {
      $("strip").innerHTML = `<b>Chưa có dữ liệu.</b> ${esc(err.message)}`;
      renderSettings();
      return;
    }
    renderToday(); renderHistory(); renderSettings();
    fillSymbols();
    if ($("p-chart").classList.contains("on")) renderChart();
  }
  const okItems = () => (D.items || []).filter((it) => it.ok);
  const barsOf = (sym, n) => ((B && B.bars && B.bars[sym]) || []).slice(-n);

  // ---------------------------------------------------------------- Hôm nay
  function width80(it) { const q = it.q["10"]; return (q["90"] - q["10"]) / it.price; }
  function sorted(items) {
    const a = items.slice();
    if (sortKey === "narrow") a.sort((x, y) => width80(x) - width80(y));
    else if (sortKey === "sym") a.sort((x, y) => x.symbol.localeCompare(y.symbol));
    else a.sort((x, y) => y.p10 - x.p10 || x.symbol.localeCompare(y.symbol));
    return a.filter((it) => it.alert).concat(a.filter((it) => !it.alert));
  }
  function renderToday() {
    const v = D.verdict || {}, items = okItems();
    $("todayKicker").textContent = `phiên ${dmy(D.trade_date)} · ${D.watchlist ? D.watchlist.n : items.length} mã`;
    const covTxt = v.cov != null ? `nón 80 % bao <b>${pct(v.cov)}</b> mã (60 phiên)` : "chưa đủ phiên để chấm";
    const psrc = D.model && D.model.p_src === "lgbm" ? "P(tăng): máy học (cổng bật)" : "P(tăng): tần suất lịch sử của ô chế độ — máy học đang tắt";
    $("strip").className = "strip " + (v.status || "pending");
    $("strip").innerHTML = `<b>${esc(v.text || "Chưa chấm")}</b> · ${covTxt} · <a href="#history">xem sổ chấm</a><br>${psrc}.`
      + (D.source && D.source.late ? " <b>Nguồn chốt muộn hôm nay.</b>" : "");
    document.querySelectorAll("#sort button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.sort === sortKey ? "true" : "false"));
    const alerts = D.alerts || [];
    const cards = sorted(items).map((it) => {
      const q10 = it.q["10"];
      return `<article class="card${it.alert ? " alert" : ""}">
        <div class="top"><div class="l"><h3><button type="button" data-chart="${esc(it.symbol)}">${esc(it.symbol)}</button></h3><span class="name">${esc(it.name)}</span></div>
          <div class="r"><span class="px">${px(it.price)}</span>${chgHtml(it.change_pct)}</div></div>
        <div class="chips">${it.alert ? `<span class="chip alert">▲ qua ngưỡng</span>` : ""}${chips(it)}</div>
        <div class="cone">${coneChart(barsOf(it.symbol, 28), it.q, it.scenarios, it.price, 326, 120)}</div>
        <div class="g3">
          <div><span class="k">P(tăng) 5p</span><span class="v">${pct(it.p5)}</span><span class="m">mốc chung ${pct(it.base5)}</span></div>
          <div><span class="k">P(tăng) 10p</span><span class="v">${pct(it.p10)}</span><span class="m">mốc chung ${pct(it.base10)}</span></div>
          <div><span class="k">Nón 80 % · +10p</span><span class="v sm">${p1(q10["10"])} – ${p1(q10["90"])}</span><span class="m">50 %: ${p1(q10["25"])} – ${p1(q10["75"])}</span></div>
        </div>
        <div class="trust"><span>n = ${it.n.toLocaleString("vi-VN")} lần lịch sử cùng ô${it.level > 0 ? ` · gộp cấp ${it.level}` : " · ô đủ 6 trục"}</span><span>${it.scenarios && it.scenarios.length ? `A ${pct(it.scenarios[0].weight)} · B ${pct(it.scenarios[1].weight)}` : ""}</span></div>
        <div class="disc">Nón là thống kê quá khứ theo chế độ hiện tại, chưa trừ phí; không phải khuyến nghị.</div>
      </article>`;
    });
    const offs = (D.items || []).filter((it) => !it.ok).map((it) => `<article class="card off"><div class="top"><div class="l"><h3>${esc(it.symbol)}</h3><span class="name">${esc(it.name)}</span></div><div class="r"><span class="px">${px(it.price)}</span></div></div><div class="reason">${esc(it.reason || "")}</div></article>`);
    const stale = (D.stale || []).map((s) => `<article class="card off"><div class="top"><div class="l"><h3>${esc(s.symbol)}</h3></div></div><div class="reason">Chưa khớp — nến cuối ${dmy(s.last_date)}. Không dự báo.</div></article>`);
    $("todayBody").innerHTML = cards.concat(offs, stale).join("") || `<div class="empty"><b>Chưa có dự báo</b>Job chưa chạy hoặc nguồn chưa chốt.</div>`;
    $("todayFoot").innerHTML = `${alerts.length} mã qua ngưỡng (P(tăng 10p) ≥ ${pct(D.settings.p_min)}, n ≥ ${D.settings.n_min}) · dữ liệu ${esc(D.generated_at ? D.generated_at.slice(11, 16) : "")} · nến ${D.source ? D.source.n_priced : "—"}/${D.watchlist ? D.watchlist.n : "—"} mã.`;
  }
  $("sort").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-sort]"); if (!b) return;
    sortKey = b.dataset.sort; try { localStorage.setItem("pp_sort", sortKey); } catch (_) {}
    renderToday();
  });

  // ---------------------------------------------------------------- Biểu đồ
  function fillSymbols() {
    const sel = $("c-sym"), items = okItems();
    sel.innerHTML = items.map((it) => `<option value="${esc(it.symbol)}">${esc(it.symbol)} — ${esc(it.name)}</option>`).join("");
    if (!cur || !items.some((it) => it.symbol === cur)) cur = items.length ? sorted(items)[0].symbol : null;
    if (cur) sel.value = cur;
  }
  function renderChart() {
    if (!D) return;
    const it = okItems().find((x) => x.symbol === cur);
    if (!it) { $("c-cone").innerHTML = `<div class="empty">Chưa có dự báo cho mã này.</div>`; return; }
    $("chartKicker").textContent = `phiên ${dmy(D.trade_date)}`;
    $("c-px").textContent = px(it.price);
    const c = it.change_pct, el = $("c-chg");
    el.className = "chg " + (c > 0 ? "up" : c < 0 ? "down" : "flat");
    el.textContent = c == null ? "" : `${c > 0 ? "▲" : c < 0 ? "▼" : "•"} ${Math.abs(c).toFixed(1)} %`;
    $("c-chips").innerHTML = chips(it);
    $("c-cone").innerHTML = coneChart(barsOf(it.symbol, 36), it.q, it.scenarios, it.price, 358, 290, { volume: true });
    $("c-scen").className = "tg " + (showScen ? "on" : "off");
    const row = (h) => { const q = it.q[h]; return `<tr><td>+${h} phiên</td><td>${p1(q["5"])}</td><td>${p1(q["25"])}</td><td>${p1(q["50"])}</td><td>${p1(q["75"])}</td><td>${p1(q["95"])}</td></tr>`; };
    $("c-table").innerHTML = `<h4>Phân vị giá (nghìn đồng) — cột X % = bao nhiêu % kịch bản nằm DƯỚI giá này</h4>
      <table><thead><tr><th>Mốc</th><th>5 %</th><th>25 %</th><th>50 %</th><th>75 %</th><th>95 %</th></tr></thead><tbody>${HS.map(row).join("")}</tbody></table>
      <div class="note">Cột 5 % ở +10 phiên = mức "xấu hiếm khi xảy ra" (đặt dừng lỗ). Cột 25 % > giá mua = lệnh có xác suất tốt. Cột 95 % = kỳ vọng lãi cực đại hợp lý.</div>`;
    const s = (D.verdict && D.verdict.s && D.verdict.s["10"]) || {};
    $("c-stats").innerHTML = `<div><span class="k">P(tăng) 5p / 10p</span><span class="v">${pct(it.p5)} / ${pct(it.p10)}</span><span class="m">mốc chung ${pct(it.base5)} / ${pct(it.base10)} · ${it.p_src === "lgbm" ? "máy học" : "tần suất ô"}</span></div>
      <div><span class="k">Độ tin cậy</span><span class="v">n = ${it.n.toLocaleString("vi-VN")}</span><span class="m">${it.level > 0 ? `gộp cấp ${it.level}` : "ô đủ 6 trục"} · hệ số giãn 80 %: ${s["80"] != null ? Number(s["80"]).toFixed(2) : "—"}</span></div>`;
    const sc = it.scenarios && it.scenarios.length ? `Hai đường vàng là <b>kịch bản A / B</b>: 2.000 đường mô phỏng gom thành hai cụm theo hình dáng, mỗi đường là tâm cụm, con số là tỷ trọng cụm. A ${pct(it.scenarios[0].weight)} nghĩa là ${pct(it.scenarios[0].weight)} đường giống A hơn B — <b>không</b> phải chắc chắn giá đi đúng A. Hai cụm gần 50/50 thì nón mới là thứ đáng nhìn.` : "";
    $("c-why").innerHTML = `<h4>Vì sao nón có hình này</h4>
      <p>Lấy ${it.n.toLocaleString("vi-VN")} lần trong lịch sử 39 mã (2015 → nay) mà cổ phiếu ở đúng ô chế độ này — ${esc((it.chips || []).join(", ") || "ô toàn cục")} — rồi xem 20 phiên sau đó giá đi đâu. Nón là phân bố của 2.000 đường mô phỏng ghép từ các đoạn đó, đã kẹp ±7 %/phiên và nới/co theo coverage thực tế.</p>
      <p>${sc}</p>
      <p class="warn">Đo walk-forward 2021–2026: nón đúng cỡ 5/5 năm; nhưng nhãn chế độ gần như không làm nón hẹp hơn, và P(tăng) chỉ hơn mốc chung rất ít. Độ rộng nón đến từ biến động của mã.</p>
      <p class="disc">Nón là thống kê quá khứ, chưa trừ phí; không phải khuyến nghị.</p>`;
  }
  $("c-sym").addEventListener("change", () => { cur = $("c-sym").value; renderChart(); });
  $("c-scen").addEventListener("click", () => { showScen = !showScen; try { localStorage.setItem("pp_scen", showScen ? "1" : "0"); } catch (_) {} renderChart(); renderToday(); });
  document.addEventListener("click", (ev) => { const el = ev.target.closest("[data-chart]"); if (el) { cur = el.dataset.chart; $("c-sym").value = cur; switchTab("chart"); } });

  // ---------------------------------------------------------------- Sổ chấm
  function renderHistory() {
    const v = D.verdict || {}, hist = (D.history || []).slice();
    $("histKicker").textContent = `đến phiên ${dmy(D.trade_date)}`;
    const big = v.status === "pending" ? "…" : pct(v.cov);
    $("verdict").innerHTML = `<div class="verdict ${esc(v.status || "pending")}"><span class="big">${big}</span><div class="t"><b>${esc(v.text || "")}</b><span>nón 80 % tại +10 phiên · cửa sổ 60 phiên${v.cov20 != null ? ` · 20 phiên gần nhất ${pct(v.cov20)}` : ""} · đúng cỡ = 74–86 %</span></div></div>`;
    // dải 30 ô: mỗi phiên một ô, coverage ngày của nón 10p phát hôm đó
    hist.sort((a, b) => a.date.localeCompare(b.date));
    const last30 = hist.slice(-30);
    const W = 334, Hh = 118, sq = (W - 2) / 30, zt = 14, zm = 44, zb = 74;
    const g = [`<rect x="0" y="0" width="${W}" height="${Hh}" fill="#fff"/>`,
      `<rect x="0" y="${zt}" width="${W}" height="30" fill="#F4E6E0"/>`, `<rect x="0" y="${zm}" width="${W}" height="30" fill="#E9EFE3"/>`, `<rect x="0" y="${zb}" width="${W}" height="30" fill="#F4E6E0"/>`];
    last30.forEach((h, i) => {
      const c = h.cov80 && h.cov80["10"]; const x = 1 + i * sq;
      if (c == null) { g.push(`<rect x="${(x + 1).toFixed(1)}" y="${zm + 4}" width="${(sq - 2).toFixed(1)}" height="22" rx="3" fill="none" stroke="${LINE}"/>`); return; }
      let yy = zm + 4, col = UP, lab = "";
      if (c > COVER_HI) { yy = zt + 4; col = DOWN; lab = "▲"; } else if (c < COVER_LO) { yy = zb + 4; col = DOWN; lab = "▼"; }
      g.push(`<rect x="${(x + 1).toFixed(1)}" y="${yy}" width="${(sq - 2).toFixed(1)}" height="22" rx="3" fill="${col}" fill-opacity="0.85"><title>${dmy(h.date)}: ${pct(c)}</title></rect>`);
      if (lab) g.push(`<text x="${(x + sq / 2).toFixed(1)}" y="${yy + 15}" font-size="8" fill="#fff" text-anchor="middle" font-family="Archivo,Arial">${lab}</text>`);
    });
    if (last30.length) {
      g.push(`<text x="4" y="${Hh - 3}" font-size="9" fill="${MUTE}" font-family="Archivo,Arial">${dmy(last30[0].date)}</text>`);
      g.push(`<text x="${W - 4}" y="${Hh - 3}" font-size="9" fill="${MUTE}" text-anchor="end" font-family="Archivo,Arial">${dmy(last30[last30.length - 1].date)} →</text>`);
    }
    g.push(`<text x="${W / 2}" y="10" font-size="9" fill="${MUTE}" text-anchor="middle" font-family="Archivo,Arial">mỗi ô = nón phát phiên đó, chấm sau 10 phiên</text>`);
    $("histGrid").innerHTML = `<h4>30 phiên gần nhất — từng phiên, nón 80 % ở +10 bao được bao nhiêu mã?</h4>
      <div class="gridwrap"><div class="lab"><span>rộng</span><span class="ok">đúng</span><span>hẹp</span></div><svg viewBox="0 0 ${W} ${Hh}" xmlns="http://www.w3.org/2000/svg" style="display:block;width:100%">${g.join("")}</svg></div>
      <div class="leg3">
        <div><i class="ok"></i><span><b>Đúng cỡ</b> — bao 74–86 % mã. Đúng như hứa.</span></div>
        <div><i class="bad">▼</i><span><b>Nón hẹp</b> — giá thật văng ra ngoài nhiều hơn dự kiến. Thị trường biến động hơn app tưởng → giảm quy mô lệnh.</span></div>
        <div><i class="bad">▲</i><span><b>Nón rộng</b> — bao gần hết, nghe hay nhưng vô dụng vì quá an toàn. App tự thu hẹp.</span></div>
      </div>
      <p class="disc" style="margin:0">39 mã cùng phiên lên xuống cùng nhau nên từng ô nhảy mạnh — một ô đỏ lẻ là bình thường. Nhìn ô lớn (60 phiên) để kết luận.</p>`;
    const mark = (c) => (c == null ? `<span style="color:${MUTE}">—</span>` : c > COVER_HI ? `<span style="color:${DOWN};font-weight:600">${pct(c)} ▲</span>` : c < COVER_LO ? `<span style="color:${DOWN};font-weight:600">${pct(c)} ▼</span>` : `<span style="color:${UP};font-weight:600">${pct(c)} ✓</span>`);
    const rows = hist.slice().reverse().map((h) => `<tr><td>${dmy(h.date)}${h.late ? ` <span class="chip p" style="padding:1px 5px">muộn</span>` : ""}</td><td class="c">${(h.alerts || []).length ? h.alerts.map((s) => `<span class="chip alert" style="padding:1px 6px">${esc(s)}</span>`).join(" ") : "—"}</td><td>${mark(h.cov80 && h.cov80["5"])}</td><td>${mark(h.cov80 && h.cov80["10"])}</td></tr>`);
    $("histTable").innerHTML = `<h4>Từng phiên</h4><table><thead><tr><th>Phiên</th><th style="text-align:center">Báo chuông</th><th>Nón 5p</th><th>Nón 10p</th></tr></thead><tbody>${rows.join("") || `<tr><td colspan="4">Chưa có phiên nào.</td></tr>`}</tbody></table>
      <div class="note">Số % = bao nhiêu mã có giá thật nằm trong nón 80 % đã vẽ 5 / 10 phiên trước. Nón vẽ hôm nay phải chờ 10 phiên nữa mới chấm được ("—").</div>`;
  }

  // ---------------------------------------------------------------- Cài đặt
  function renderSettings() {
    if (D) {
      const s = D.settings || {};
      $("thresholds").innerHTML = `<div class="l"><span>Ngưỡng P(tăng 10p)</span><span class="pill n">≥ ${pct(s.p_min)}</span></div>
        <div class="l"><span>Số mẫu tối thiểu trong ô</span><span class="pill n">${s.n_min} lần</span></div>
        <div class="l"><span>Gộp khi nhiều mã</span><span class="pill n">> ${s.digest_threshold} mã</span></div>
        <div class="l"><span>Nhịp tim thứ Hai</span><span class="pill ${s.heartbeat ? "on" : "off"}">${s.heartbeat ? "bật" : "tắt"}</span></div>
        <div class="h">Đo 2021–2026: chỉ ~15 % phiên-mã có P(tăng 10p) ≥ 0,58, ~8 % ≥ 0,60. Đổi ngưỡng: sửa <span class="mono">docs/data/settings.json</span> rồi push — job chạy lại ngay.</div>`;
      const gate = (D.model && D.model.gate) || {}, per = (gate.per_h && gate.per_h["10"]) || {}, rows = (gate.rows && gate.rows["10"]) || [];
      const tr = rows.map((r) => `<tr><td>${r.year}</td><td>${(r.acc_lgbm * 100).toFixed(1)} / ${(r.acc_always_up * 100).toFixed(1)}</td><td>${r.brier_lgbm.toFixed(4)} / ${r.brier_freq.toFixed(4)}</td><td class="c">${r.brier_lgbm < r.brier_freq && r.acc_lgbm > r.acc_always_up ? `<span style="color:${UP};font-weight:700">✓</span>` : `<span style="color:${DOWN};font-weight:700">✗</span>`}</td></tr>`);
      $("gateBody").innerHTML = `<div class="srow"><div class="l"><span>Trạng thái</span><span class="pill ${gate.enabled ? "on" : "off"}">${gate.enabled ? "BẬT" : "TẮT"}${per.wins_brier ? ` · Brier thắng ${per.wins_brier}, đúng thắng ${per.wins_acc}` : ""}</span></div>
        <div class="h">Cổng tự động: chỉ bật khi thắng mốc "luôn tăng" VÀ Brier tốt hơn tần suất ô ở ≥ ${per.need || 4}/5 năm trọn. ${gate.enabled ? "Đang dùng máy học." : "App đang dùng tần suất theo ô chế độ."}</div></div>
        ${rows.length ? `<div class="tbl" style="margin:8px 0 0;padding:6px 0 0"><table><thead><tr><th>Năm</th><th>Đúng % · LGBM / luôn tăng</th><th>Brier · LGBM / ô</th><th style="text-align:center">Đạt</th></tr></thead><tbody>${tr.join("")}</tbody></table></div>` : ""}
        <div class="h" style="margin-top:6px">Walk-forward h = 10 phiên: học tới hết năm trước, thử năm sau${gate.trained_at ? ` · huấn luyện ${dmy(gate.trained_at)}` : ""}. Máy học bám vào đặc trưng VN-Index (39 mã cùng ngày cùng giá trị) nên áp chế độ năm cũ sang năm mới — đó là lý do thua.</div>`;
      const v = D.verdict || {}, sc = v.s || {};
      const srow = (h) => `<tr><td>+${h} phiên</td>${["50", "80", "90"].map((lv) => `<td>${sc[h] && sc[h][lv] != null ? Number(sc[h][lv]).toFixed(2) : "—"}</td>`).join("")}</tr>`;
      $("coneParams").innerHTML = `<div class="srow"><div class="l"><span>Kẹp biên độ ±7 %/phiên</span><span class="pill on">bật</span></div><div class="h">HOSE ±7 %. Mã HNX/UPCoM (±10/15 %) hơi bị hẹp — 1–2 mã trong danh mục.</div>
        <div class="l"><span>Chấm coverage theo ngày</span><span class="pill on">bật</span></div><div class="h">39 mã cùng phiên không độc lập — mỗi ngày một con số cho cả danh mục, cửa sổ ${v.window || 60} phiên.</div>
        <div class="l"><span>Tốc độ tự chỉnh γ</span><span class="pill n">0,05</span></div><div class="h">s ← s·exp(γ·(mục tiêu − tỷ lệ trúng)); s trong [0,5; 3].</div></div>
        <div class="tbl" style="margin:8px 0 0;padding:6px 0 0"><h4>Hệ số giãn hiện tại (1,00 = nón thô)</h4><table><thead><tr><th>Mốc</th><th>50 %</th><th>80 %</th><th>90 %</th></tr></thead><tbody>${HS.map(srow).join("")}</tbody></table></div>`;
      const src = D.source || {}, m = D.model || {};
      $("sysBody").innerHTML = `Job 15:40 T2–T6 (dự phòng 16:10 · 16:50 · 18:15) · dữ liệu đến phiên <b>${dmy(D.trade_date)}</b>, sinh ${esc((D.generated_at || "").slice(0, 16).replace("T", " "))}<br>
        Nguồn DNSE ${src.dnse_ok ? "OK" : `<b style="color:${DOWN}">lỗi</b>`} · ${src.n_priced}/${D.watchlist ? D.watchlist.n : "—"} mã có nến${src.unsettled && src.unsettled.length ? ` · chưa chốt: ${esc(src.unsettled.join(", "))}` : ""}${src.late ? " · chốt muộn" : ""}${(D.stale || []).length ? ` · nến cũ: ${esc(D.stale.map((s) => s.symbol).join(", "))}` : ""}<br>
        Kho ${(src.history_rows || 0).toLocaleString("vi-VN")} phiên-mã · pool ${(m.pool_global || 0).toLocaleString("vi-VN")} · ${m.cells_full || 0} ô đủ 6 trục · danh mục ${D.watchlist ? esc(D.watchlist.source) : "—"}`;
    }
    fetch("data/state.json", { cache: "no-cache" }).then((r) => (r.ok ? r.json() : null)).then((st) => {
      if (!st) return;
      const dv = st.devices || {}, p = st.push || {};
      let s = `Job chạy lần cuối ${st.last_run ? esc(st.last_run.slice(0, 16).replace("T", " ")) : "—"} · ${dv.n || 0} máy đã đăng ký (${esc(dv.source || "—")}) · VAPID ${dv.vapid ? "OK" : "THIẾU"}`;
      if (p.mode) s += ` · lần báo gần nhất: ${esc(p.mode)}, gửi ${p.sent || 0}`;
      if (p.errors && p.errors.length) s += ` · <b>${esc(p.errors[0])}</b>`;
      if (st.push_gone_at) s += ` · <b>có máy đã huỷ đăng ký (${esc(st.push_gone_at.slice(0, 10))}) — bấm Bật thông báo lại</b>`;
      $("stateFoot").innerHTML = s;
    }).catch(() => {});
  }

  // ---------------------------------------------------------------- push (chép candle-radar)
  const b64ToU8 = (s) => { const p = "=".repeat((4 - s.length % 4) % 4); const b = atob((s + p).replace(/-/g, "+").replace(/_/g, "/")); return Uint8Array.from(b, (c) => c.charCodeAt(0)); };
  const SW = "sw.js?v=1";
  async function pushStatus() {
    const st = $("pushState");
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) { st.textContent = "Trình duyệt này không hỗ trợ thông báo đẩy."; $("pushBtn").disabled = true; return; }
    if (!CFG.VAPID_PUBLIC) { st.textContent = "Chưa có VAPID_PUBLIC trong config.js — chạy job.gen_vapid rồi dán khoá công khai vào docs/config.js."; $("pushBtn").disabled = true; return; }
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (sub) {
      st.textContent = CFG.WORKER_URL ? "Máy này đã đăng ký." : "Máy này đã tạo địa chỉ nhận · đảm bảo đoạn mã bên dưới đã được dán vào GitHub.";
      $("pushBtn").textContent = "Đăng ký lại"; $("testBtn").hidden = !CFG.WORKER_URL;
      if (!CFG.WORKER_URL) showSubCode(sub);
    } else { st.textContent = "Máy này chưa đăng ký nhận thông báo."; }
  }
  function showSubCode(sub) {
    const code = JSON.stringify([sub.toJSON()]);
    $("subCodeWrap").innerHTML = `<div class="subcode"><b>Đoạn mã đăng ký của máy này.</b> Dán vào GitHub → Settings → Secrets and variables → Actions → <span class="mono">PUSH_SUBS_FALLBACK</span> (nhiều máy thì nối các đoạn trong cùng một mảng JSON). Làm một lần mỗi máy.
      <textarea id="subTxt" readonly></textarea><div class="btns" style="margin-top:6px"><button type="button" class="btn" id="copySub">Sao chép</button></div></div>`;
    $("subTxt").value = code;
    $("copySub").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(code); toast("Đã sao chép", "Dán vào GitHub Secret PUSH_SUBS_FALLBACK."); }
      catch (_) { $("subTxt").select(); document.execCommand("copy"); toast("Đã sao chép", ""); }
    });
  }
  const swReady = () => Promise.race([
    navigator.serviceWorker.ready,
    new Promise((_, rej) => setTimeout(() => rej(new Error("Phần chạy nền chưa sẵn sàng — đóng hẳn app, mở lại rồi bấm lần nữa")), 8000)),
  ]);
  $("pushBtn").addEventListener("click", async () => {
    const st = $("pushState"), btn = $("pushBtn");
    btn.disabled = true;
    try {
      if (Notification.permission === "denied") { st.textContent = "Điện thoại đang CHẶN thông báo của trang này. Mở Cài đặt trình duyệt → Cài đặt trang web → Thông báo → bật, rồi bấm lại."; return; }
      st.textContent = "Đang xin quyền thông báo… (nếu hiện hộp thoại, bấm Cho phép)";
      const perm = await Notification.requestPermission();
      if (perm !== "granted") { st.textContent = "Chưa cho phép. Bấm lại và chọn Cho phép."; return; }
      st.textContent = "Đang chuẩn bị phần chạy nền…";
      if (!navigator.serviceWorker.controller) { try { await navigator.serviceWorker.register(SW); } catch (_) { /* thử tiếp */ } }
      const reg = await swReady();
      st.textContent = "Đang tạo địa chỉ nhận với Google…";
      let sub = await reg.pushManager.getSubscription();
      if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToU8(CFG.VAPID_PUBLIC) });
      if (CFG.WORKER_URL) {
        const r = await fetch(CFG.WORKER_URL + "/subscribe", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.assign({ ua: navigator.userAgent.slice(0, 120) }, sub.toJSON())) });
        if (!r.ok) throw new Error("Worker trả lỗi " + r.status);
        toast("Đã đăng ký máy này", "Từ giờ thông báo sau phiên sẽ tới đây.");
      } else {
        toast("Đã tạo địa chỉ nhận", "Sao chép đoạn mã bên dưới và dán vào GitHub — một lần cho máy này.");
      }
      await pushStatus();
    } catch (err) {
      st.textContent = "Không đăng ký được: " + (err && err.message ? err.message : err) + " — chụp màn hình dòng này gửi lại.";
    } finally { btn.disabled = false; }
  });
  $("testBtn").addEventListener("click", async () => {
    try {
      const r = await fetch(CFG.WORKER_URL + "/test", { method: "POST" });
      toast(r.ok ? "Đã yêu cầu gửi thử" : "Gửi thử lỗi " + r.status, r.ok ? "Thông báo thật sẽ tới trong vài giây." : "");
    } catch (err) { alert(err.message); }
  });
  let toastTimer = null;
  function toast(t, b) { $("toastTitle").textContent = t; $("toastBody").textContent = b || ""; $("toast").classList.add("on"); clearTimeout(toastTimer); toastTimer = setTimeout(() => $("toast").classList.remove("on"), 5000); }
  $("toast").addEventListener("click", () => $("toast").classList.remove("on"));

  // ---------------------------------------------------------------- tab + khởi động
  const tabs = document.querySelectorAll('nav[role="tablist"] button');
  function switchTab(name) {
    tabs.forEach((x) => x.setAttribute("aria-selected", x.dataset.tab === name ? "true" : "false"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("on", p.id === "p-" + name));
    $("main").scrollTop = 0;
    if (name === "chart") renderChart();
  }
  tabs.forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));
  function applyHash() { const m = /^#(today|history|chart|settings)$/.exec(location.hash); if (m) switchTab(m[1]); }
  window.addEventListener("hashchange", applyHash);
  if ("serviceWorker" in navigator) navigator.serviceWorker.register(SW).catch(() => {});
  load().then(() => { applyHash(); pushStatus(); });
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") load(); });
})();
