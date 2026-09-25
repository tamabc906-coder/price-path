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
  // opts.volume: dải KL · opts.fill: màu nón · opts.path: giá đóng cửa THẬT các phiên sau mốc (nón sự kiện neo ở quá khứ)
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
    const real = opts.path || [];
    real.forEach((p) => { lo = Math.min(lo, p); hi = Math.max(hi, p); });
    const FILL = opts.fill || INK;
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
      out.push(`<polygon points="${up.concat(dn).join(" ")}" fill="${FILL}" fill-opacity="${op}"/>`);
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
    out.push(`<polyline points="${med.join(" ")}" fill="none" stroke="${FILL}" stroke-width="1.2" stroke-dasharray="3 2"/>`);
    if (real.length) {
      const pts = [`${f1(xt(0))},${f1(y(price0))}`].concat(real.map((p, k) => `${f1(xt(k + 1))},${f1(y(p))}`));
      out.push(`<polyline points="${pts.join(" ")}" fill="none" stroke="${GOLDC}" stroke-width="2.2" stroke-linejoin="round"/>`);
      const lx = xt(real.length), ly = y(real[real.length - 1]);
      out.push(`<circle cx="${f1(lx)}" cy="${f1(ly)}" r="3" fill="${GOLDC}"/>`);
      out.push(`<text x="${f1(lx + 5)}" y="${f1(ly + 3)}" font-size="8.5" font-weight="700" fill="${GOLD2}" font-family="Archivo,Arial">nay ${px(real[real.length - 1])}</text>`);
    }
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
    out.push(`<text x="${f1(xLast)}" y="${H - 4}" font-size="8" fill="${GOLDC}" text-anchor="middle" font-family="Archivo,Arial">${esc(opts.anchor || "nay")}</text>`);
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

  // ---------------------------------------------------------------- Sự kiện (model/events.py, job E2)
  // Thứ duy nhất đo ra có HƯỚNG: nón lịch sử sau sự kiện, neo tại giá đóng cửa ngày sự kiện, đường vàng = giá thật đã đi.
  const EV_FILL = "#3B2A6B";
  const spc = (v, d) => (v == null ? "—" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(d == null ? 1 : d).replace(".", ",")} %`);
  const evMeta = () => (D && D.events_meta) || { enabled: [], push: [], stats: {}, alert_mode: "p10" };
  const evMode = () => evMeta().alert_mode === "events";
  const evAll = () => okItems().flatMap((it) => (it.events || []).map((e) => ({ it, e }))).sort((a, b) => a.e.age - b.e.age || a.it.symbol.localeCompare(b.it.symbol));
  const ageTxt = (a) => (a === 0 ? "hôm nay" : `${a} phiên trước`);
  function barsUpTo(sym, iso, n) { const all = (B && B.bars && B.bars[sym]) || []; return all.filter((b) => b[0] <= iso).slice(-n); }
  function evChart(it, e, W, H, volume) {
    if (!e.q) return `<div class="empty">Chưa đủ lần lịch sử (${e.n_pool}) để vẽ nón cho sự kiện này.</div>`;
    const bs = barsUpTo(it.symbol, e.date, volume ? 30 : 22);
    if (!bs.length) return "";
    return coneChart(bs, e.q, null, e.price0, W, H, { path: e.path.slice(1), fill: EV_FILL, anchor: dmy(e.date), volume: !!volume });
  }
  function evStatsHtml(e) {
    const st = e.stats || {}, q = e.q && e.q["10"];
    return `<div class="g3">
      <div><span class="k">Lịch sử · 10p</span><span class="v">${spc(st.ex10)}</span><span class="m">vượt mốc · đúng ${st.years_win}/${st.years} năm</span></div>
      <div><span class="k">Chạm +5 % trước −5 %</span><span class="v">${e.p_touch == null ? "—" : pct(e.p_touch)}</span><span class="m">trong 10 phiên</span></div>
      <div><span class="k">Nón 80 % · +10p</span><span class="v sm">${q ? `${p1(q["10"])} – ${p1(q["90"])}` : "—"}</span><span class="m">tâm ${q ? p1(q["50"]) : "—"}</span></div>
    </div>`;
  }
  function evCard(it, e) {
    const pushed = (it.alert_events || []).includes(e.code) && e.age === 0;
    const move = e.path.length > 1 ? e.path[e.path.length - 1] / e.price0 - 1 : null;
    return `<article class="card ev${pushed ? " alert" : ""}">
      <div class="top"><div class="l"><h3><button type="button" data-chart="${esc(it.symbol)}">${esc(it.symbol)}</button></h3><span class="name">${esc(it.name)}</span></div>
        <div class="r"><span class="px">${px(it.price)}</span>${chgHtml(it.change_pct)}</div></div>
      <div class="chips"><span class="chip ev">${esc(e.name)}</span><span class="chip">${dmy(e.date)} · ${ageTxt(e.age)}</span>${pushed ? `<span class="chip alert">🔔 đã báo</span>` : ""}${move != null ? `<span class="chip ${move >= 0 ? "g" : "r"}">từ sự kiện ${spc(move)}</span>` : ""}</div>
      <div class="cone">${evChart(it, e, 326, 130)}</div>
      ${evStatsHtml(e)}
      <div class="trust"><span>nón từ ${(e.n_pool || 0).toLocaleString("vi-VN")} lần sự kiện này trong lịch sử 39 mã · neo giá ${px(e.price0)} ngày ${dmy(e.date)}</span></div>
      <div class="disc">Lãi lịch sử là vượt mua-đại, sau phí; nón là thống kê quá khứ, không phải khuyến nghị.</div>
    </article>`;
  }
  function renderEvents() {
    const el = $("evBlock"), m = evMeta();
    if (!m.enabled || !m.enabled.length) { el.innerHTML = ""; return; }
    const list = evAll(), names = m.enabled.map((k) => (m.stats[k] && m.stats[k].name) || k);
    const lastEv = (D.event_log || [])[0];
    const head = `<div class="evhead"><h2>Sự kiện có lợi thế${list.length ? ` · ${list.length}` : ""}</h2><span>hiện ${m.active_days || 10} phiên sau khi xảy ra</span></div>`;
    if (!list.length) {
      el.innerHTML = `${head}<div class="box evnone"><p><b>Hôm nay không mã nào có lợi thế hướng.</b> App chỉ nói hướng khi có sự kiện đã đo đạt cổng: ${esc(names.join(" · "))}. Các nón bên dưới chỉ là thước biên độ — P(tăng) ≈ mốc chung.</p>
        ${lastEv ? `<p class="m">Lần gần nhất: <b>${esc(lastEv.symbol)}</b> · ${esc(lastEv.event)} · ${dmy(lastEv.date)}${lastEv.ret10 != null ? ` → sau 10 phiên ${spc(lastEv.ret10)}` : ""} · <a href="#history">xem nhật ký</a></p>` : ""}</div>`;
      return;
    }
    el.innerHTML = head + `<div class="cards evcards">${list.map(({ it, e }) => evCard(it, e)).join("")}</div>`;
  }

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
    const psrc = D.model && D.model.p_src === "lgbm" ? "P(tăng): máy học (cổng bật)"
      : evMode() ? "Nón = thước biên độ; P(tăng) ≈ mốc chung (đo 2021–2026). Hướng chỉ có ở khối Sự kiện" : "P(tăng): tần suất lịch sử của ô chế độ — máy học đang tắt";
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
        <div class="chips">${it.alert ? `<span class="chip alert">${evMode() ? "🔔 sự kiện" : "▲ qua ngưỡng"}</span>` : ""}${(it.events || []).map((e) => `<span class="chip ev">${esc(e.name)} · ${ageTxt(e.age)}</span>`).join("")}${chips(it)}</div>
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
    const m = evMeta(), pushNames = (m.push || []).map((k) => (m.stats[k] && m.stats[k].name) || k);
    renderEvents();
    $("todayFoot").innerHTML = (evMode() ? `${alerts.length} mã có sự kiện mới được báo (push: ${esc(pushNames.join(", ") || "không")})`
      : `${alerts.length} mã qua ngưỡng (P(tăng 10p) ≥ ${pct(D.settings.p_min)}, n ≥ ${D.settings.n_min})`) + ` · dữ liệu ${esc(D.generated_at ? D.generated_at.slice(11, 16) : "")} · nến ${D.source ? D.source.n_priced : "—"}/${D.watchlist ? D.watchlist.n : "—"} mã.`;
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
    if (!cur || !items.some((it) => it.symbol === cur)) {
      const ev = evAll()[0];                                   // có sự kiện thì mở mã đó trước
      cur = ev ? ev.it.symbol : items.length ? sorted(items)[0].symbol : null;
    }
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
    const evs = it.events || [];
    $("c-ev").hidden = !evs.length;
    $("c-ev").innerHTML = evs.map((e) => `<h4>Nón sau sự kiện · ${esc(e.name)} · ${dmy(e.date)} (${ageTxt(e.age)})</h4>
      <div class="cone big">${evChart(it, e, 358, 250, true)}</div>
      <div class="legend"><span><i class="o35 ev"></i>50 %</span><span><i class="o2 ev"></i>80 %</span><span><i class="o1 ev"></i>90 %</span><span><i class="sa"></i>giá thật từ ngày sự kiện</span></div>
      ${evStatsHtml(e)}
      <p>Nón dựng từ ${(e.n_pool || 0).toLocaleString("vi-VN")} lần "${esc(e.name)}" trong lịch sử 39 mã: đường đi 20 phiên sau mỗi lần, chuẩn hoá theo biến động rồi nhân lại biến động của ${esc(it.symbol)} ngày ${dmy(e.date)}, nới thêm cho đủ độ bao đã đo. Khác nón chế độ ở trên: nón này <b>nghiêng</b> vì sự kiện đã đo có lợi thế (${spc(e.stats && e.stats.ex10)}/10p vượt mua-đại, đúng ${e.stats && e.stats.years_win}/${e.stats && e.stats.years} năm).</p>`).join("");
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

  // ---------------------------------------------------------------- Vùng giá (zone/)
  // Đọc data/zone/latest.json do zone/run_daily.py ghi — tải lười khi mở tab, độc lập với latest.json.
  let Z = null, zcur = null, zwin = "40", zbig = false, zLoading = false;
  try { zwin = localStorage.getItem("pp_zwin") || "40"; } catch (_) {}
  const vol = (v) => (v == null ? "—" : v >= 1e6 ? (v / 1e6).toFixed(v >= 1e7 ? 0 : 1) + " tr" : v >= 1e3 ? Math.round(v / 1e3) + " k" : String(v));
  const zsym = () => (Z && Z.symbols && Z.symbols[zcur]) || null;

  async function loadZone() {
    if (zLoading) return;
    zLoading = true;
    try {
      const r = await fetch("data/zone/latest.json", { cache: "no-cache" });
      if (!r.ok) throw new Error("Chưa có data/zone/latest.json — job vùng giá chưa chạy lần nào.");
      Z = await r.json();
      const syms = Object.keys(Z.symbols || {}).sort();
      $("z-sym").innerHTML = syms.map((k) => `<option value="${esc(k)}">${esc(k)} — ${esc(Z.symbols[k].name)}</option>`).join("");
      if (!zcur || !Z.symbols[zcur]) zcur = (cur && Z.symbols[cur]) ? cur : syms[0] || null;
      if (zcur) $("z-sym").value = zcur;
    } catch (err) {
      $("z-strip").innerHTML = `<b>Chưa có dữ liệu.</b> ${esc(err.message)}`;
      Z = null;
    }
    zLoading = false;
  }

  // Profile ngang: mỗi ô giá một hàng, thanh = mua (xanh) + bán (đỏ) + ATO/ATC (xám); mờ dần theo phần ước lượng.
  function profileChart(p, price, W, big) {
    const bins = p.bins, n = bins.length, w = p.bin;
    const rowH = n > 40 ? 7 : n > 25 ? 9 : 12, top = 8, bot = 22, left = 44, right = 10;
    const H = top + n * rowH + bot, plotW = W - left - right;
    const tot = (b) => (big ? b[4] + b[5] : b[1] + b[2] + b[3]);
    const vmax = Math.max(1, ...bins.map(tot));
    const yTop = (i) => top + (n - 1 - i) * rowH;           // ô cao nhất ở trên
    const yPrice = (v) => top + (n - (v - p.base) / w) * rowH;
    const f1 = (v) => Math.round(v * 10) / 10;
    const out = [`<rect width="${W}" height="${H}" fill="#fff"/>`];
    // Value Area
    out.push(`<rect x="${left}" y="${f1(yTop(p.va[1]))}" width="${plotW}" height="${f1((p.va[1] - p.va[0] + 1) * rowH)}" fill="${GOLD}" fill-opacity="0.16"/>`);
    // Vùng mua/bán: dải màu sát trục giá
    const zl = big ? [[p.big_buy_zones, UP], [p.big_sell_zones, DOWN]] : [[p.buy_zones, UP], [p.sell_zones, DOWN]];
    zl.forEach(([zs, col]) => (zs || []).forEach((z) => {
      const i0 = Math.round((z.lo - p.base) / w), i1 = Math.round((z.hi - p.base) / w) - 1;
      out.push(`<rect x="${left - 4}" y="${f1(yTop(i1))}" width="3" height="${f1((i1 - i0 + 1) * rowH)}" fill="${col}"/>`);
    }));
    // Thanh
    bins.forEach((b, i) => {
      const t = tot(b); if (t <= 0) return;
      const y = yTop(i) + 1, h = rowH - 2, k = plotW / vmax;
      const est = big ? 0 : (b[6] || 0) / (b[1] + b[2] + b[3]);
      const op = 1 - 0.55 * est;
      const segs = big ? [[b[4], UP], [b[5], DOWN]] : [[b[1], UP], [b[2], DOWN], [b[3], "#B8B3A6"]];
      let x = left;
      segs.forEach(([v, col]) => { if (v > 0) { out.push(`<rect x="${f1(x)}" y="${f1(y)}" width="${f1(Math.max(0.6, v * k))}" height="${f1(h)}" fill="${col}" fill-opacity="${op.toFixed(2)}"/>`); x += v * k; } });
    });
    // POC + VAH/VAL (mép trên/dưới dải Value Area). Nhãn gom lại rồi dời cho khỏi đè — chỉ dời chữ, không dời vạch.
    const labs = [];
    const yPoc = f1(yTop(p.poc) + rowH / 2), yVah = f1(yTop(p.va[1])), yVal = f1(yTop(p.va[0]) + rowH);
    out.push(`<line x1="${left}" y1="${yVah}" x2="${W - right}" y2="${yVah}" stroke="${GOLD2}" stroke-width="1" stroke-dasharray="3 2"/>`);
    out.push(`<line x1="${left}" y1="${yVal}" x2="${W - right}" y2="${yVal}" stroke="${GOLD2}" stroke-width="1" stroke-dasharray="3 2"/>`);
    out.push(`<line x1="${left}" y1="${yPoc}" x2="${W - right}" y2="${yPoc}" stroke="${GOLDC}" stroke-width="1.5"/>`);
    labs.push({ y: yVah - 2, t: `VAH ${px(bins[p.va[1]][0] + w)}`, c: GOLD2, b: false });
    labs.push({ y: yPoc - 2, t: `POC ${px(bins[p.poc][0] + w / 2)}`, c: GOLD2, b: false });
    labs.push({ y: yVal + 8, t: `VAL ${px(bins[p.va[0]][0])}`, c: GOLD2, b: false });
    // Nhãn giá: ≤ 10 nhãn
    const step = Math.max(1, Math.ceil(n / 10));
    for (let i = 0; i < n; i += step) out.push(`<text x="${left - 7}" y="${f1(yTop(i) + rowH / 2 + 3)}" font-size="8.5" fill="${MUTE}" text-anchor="end" font-family="Archivo,Arial">${px(bins[i][0])}</text>`);
    // Giá hiện tại
    if (price != null && price >= p.base && price <= p.base + n * w) {
      const y = f1(yPrice(price));
      out.push(`<line x1="${left - 6}" y1="${y}" x2="${W - right}" y2="${y}" stroke="#3B2A6B" stroke-width="1.2" stroke-dasharray="3 2"/>`);
      labs.push({ y: y - 2, t: `giá ${px(price)}`, c: "#3B2A6B", b: true });
    }
    // Mức giá chính xác mua / bán chủ động nhiều nhất (#1 của bảng top) — vạch ngắn + nhãn ▲ ▼.
    const tl = p.top || {};
    [[(big ? tl.big_buy : tl.buy) || [], UP, "▲ mua"], [(big ? tl.big_sell : tl.sell) || [], DOWN, "▼ bán"]].forEach(([rows, col, t]) => {
      if (!rows.length) return;
      const y = f1(yPrice(rows[0].p));
      out.push(`<line x1="${W - right - 40}" y1="${y}" x2="${W - right}" y2="${y}" stroke="${col}" stroke-width="1.5"/>`);
      labs.push({ y: y - 2, t: `${t} ${px(rows[0].p)}`, c: col, b: true });
    });
    labs.sort((a, b) => a.y - b.y);
    let last = -1e9;
    labs.forEach((l) => {
      const y = Math.max(l.y, last + 9);
      last = y;
      out.push(`<text x="${W - right}" y="${f1(y)}" font-size="8" fill="${l.c}" text-anchor="end" font-family="Archivo,Arial" stroke="#fff" stroke-width="2.5" paint-order="stroke"${l.b ? ' font-weight="700"' : ""}>${l.t}</text>`);
    });
    out.push(`<text x="${left}" y="${H - 6}" font-size="8" fill="${MUTE}" font-family="Archivo,Arial">0</text>`);
    out.push(`<text x="${W - right}" y="${H - 6}" font-size="8" fill="${MUTE}" text-anchor="end" font-family="Archivo,Arial">${vol(vmax)} / ô ${px(w)}</text>`);
    return `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Khối lượng theo mức giá">${out.join("")}</svg>`;
  }

  function zoneTable(id, title, zones, kind) {
    const list = (zones || []).slice().sort((a, b) => Math.abs(a.dist || 0) - Math.abs(b.dist || 0));
    if (!list.length) { $(id).innerHTML = `<h4>${title} <span class="n">— không có ô nào vượt ngưỡng</span></h4>`; return; }
    const rows = list.map((z) => {
      const d = z.dist == null ? "—" : `${z.dist > 0 ? "+" : ""}${z.dist.toFixed(1)} %`;
      const est = z.est_share >= 0.5 ? `<span class="est">ước lượng ${Math.round(z.est_share * 100)} %</span>` : "";
      return `<tr><td>${px(z.lo)} – ${px(z.hi)}${est}<span class="z">${z.sessions} phiên · gần nhất ${dmy(z.last)}</span></td><td>${vol(z.vol)}</td><td class="share ${kind}"><b>${pct(z.share)}</b></td><td>${d}</td></tr>`;
    }).join("");
    $(id).innerHTML = `<h4>${title} <span class="n">— ${list.length} vùng, gần giá nhất trước</span></h4>
      <table><thead><tr><th>Vùng giá</th><th>KL</th><th>% mua</th><th>Cách giá</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  // Mức giá CHÍNH XÁC (không gộp ô) có KL mua / bán chủ động lớn nhất trong khung — profiles[w].top.
  function topTable(id, title, rows, side) {
    if (!rows || !rows.length) { $(id).innerHTML = `<h4>${title} <span class="n">— không có (nguồn không ghi bên chủ động)</span></h4>`; return; }
    const body = rows.map((r, i) => {
      const d = r.dist == null ? "—" : `${r.dist > 0 ? "+" : ""}${r.dist.toFixed(1)} %`;
      const est = r.est_share >= 0.5 ? `<span class="est">ước lượng ${Math.round(r.est_share * 100)} %</span>` : "";
      return `<tr><td><b>${i + 1}.</b> ${px(r.p)}${est}<span class="z">${pct(r.share)} mua tại giá · ${r.sessions} phiên · gần nhất ${dmy(r.last)}</span></td><td>${vol(r.vol)}</td><td class="share ${side === "mua" ? "up" : "down"}"><b>${pct(r.pct)}</b></td><td>${d}</td></tr>`;
    }).join("");
    $(id).innerHTML = `<h4>${title} <span class="n">— ${rows.length} mức giá, lớn nhất trước</span></h4>
      <table><thead><tr><th>Giá</th><th>KL ${side}</th><th>% tổng ${side}</th><th>Cách giá</th></tr></thead><tbody>${body}</tbody></table>`;
  }

  // ---- Mua/bán chủ động theo phiên (latest.symbols[m].daily, profiles[w].flow, latest.market) ----
  let zmode = "sym", zmsort = "buy";
  const sgn = (v) => (v > 0 ? "+" : v < 0 ? "−" : "");
  const svol = (v) => (v == null ? "—" : sgn(v) + vol(Math.abs(v)));
  const bil = (v) => (v == null ? "—" : Number(v).toFixed(v >= 100 ? 0 : 1));
  const sbil = (v) => (v == null ? "—" : sgn(v) + Math.abs(v).toFixed(Math.abs(v) >= 100 ? 0 : 1));
  const cls = (v) => (v > 0 ? "up" : v < 0 ? "down" : "");

  // Cột = ròng (mua CĐ − bán CĐ) mỗi phiên; đường vàng = ròng cộng dồn trên thang riêng.
  function flowChart(rows, W) {
    const n = rows.length, H = 128, top = 10, bot = 18, left = 8, right = 8;
    const plotW = W - left - right, mid = top + (H - top - bot) / 2, half = (H - top - bot) / 2;
    const m = Math.max(1, ...rows.map((r) => Math.abs(r.net)));
    let c = 0;
    const cum = rows.map((r) => (c += r.net));
    const cm = Math.max(1, ...cum.map((v) => Math.abs(v)));
    const bw = plotW / n, f1 = (v) => Math.round(v * 10) / 10;
    const out = [`<rect width="${W}" height="${H}" fill="#fff"/>`,
      `<line x1="${left}" y1="${mid}" x2="${W - right}" y2="${mid}" stroke="${LINE}" stroke-width="1"/>`];
    rows.forEach((r, i) => {
      const h = (Math.abs(r.net) / m) * half, x = left + i * bw + bw * 0.15;
      const y = r.net >= 0 ? mid - h : mid;
      out.push(`<rect x="${f1(x)}" y="${f1(y)}" width="${f1(Math.max(1, bw * 0.7))}" height="${f1(Math.max(0.6, h))}" fill="${r.net >= 0 ? UP : DOWN}" fill-opacity="${r.est ? 0.35 : 0.9}"/>`);
    });
    const pts = cum.map((v, i) => `${f1(left + i * bw + bw / 2)},${f1(mid - (v / cm) * half)}`).join(" ");
    out.push(`<polyline points="${pts}" fill="none" stroke="${GOLDC}" stroke-width="1.6"/>`);
    out.push(`<text x="${left}" y="${H - 5}" font-size="8.5" fill="${MUTE}" font-family="Archivo,Arial">${dmy(rows[0].d)}</text>`);
    out.push(`<text x="${W - right}" y="${H - 5}" font-size="8.5" fill="${MUTE}" text-anchor="end" font-family="Archivo,Arial">${dmy(rows[n - 1].d)}</text>`);
    out.push(`<text x="${W - right}" y="${top + 1}" font-size="8.5" fill="${GOLD2}" text-anchor="end" font-family="Archivo,Arial" stroke="#fff" stroke-width="2.5" paint-order="stroke">cộng dồn ${svol(cum[n - 1])}</text>`);
    return `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Ròng mua bán chủ động theo phiên">${out.join("")}</svg>`;
  }

  function renderFlow(s, p) {
    const el = $("z-flow");
    const all = s.daily || [];
    const rows = all.slice(-p.n);
    if (!rows.length) { el.innerHTML = ""; return; }
    const t = p.flow || {};
    const body = rows.slice().reverse().map((r) => `<tr><td>${dmy(r.d)}${r.est ? '<span class="est">ước lượng</span>' : ""}${r.no_side ? '<span class="est">không có bên CĐ</span>' : ""}</td>` +
      `<td>${vol(r.buy)}</td><td>${vol(r.sell)}</td><td class="share ${r.buy_share >= 0.5 ? "up" : "down"}"><b>${pct(r.buy_share)}</b></td>` +
      `<td class="${cls(r.net)}">${svol(r.net)}</td><td>${vol(r.x)}</td>` +
      `<td>${bil(r.big_buy_val)}</td><td>${bil(r.big_sell_val)}</td><td class="${cls(r.big_net_val)}">${sbil(r.big_net_val)}</td></tr>`).join("");
    const foot = `<tr class="sum"><td>Tổng ${t.n || rows.length} phiên</td><td>${vol(t.buy)}</td><td>${vol(t.sell)}</td>` +
      `<td class="share ${t.buy_share >= 0.5 ? "up" : "down"}"><b>${pct(t.buy_share)}</b></td><td class="${cls(t.net)}">${svol(t.net)}</td><td>${vol(t.x)}</td>` +
      `<td>${bil(t.big_buy_val)}</td><td>${bil(t.big_sell_val)}</td><td class="${cls(t.big_net_val)}">${sbil(t.big_net_val)}</td></tr>`;
    el.innerHTML = `<h4>Mua / bán chủ động theo phiên <span class="n">— ${rows.length} phiên, cột = mua CĐ − bán CĐ</span></h4>
      <div class="fchart">${flowChart(rows, 342)}</div>
      <div class="scroll"><table class="wide"><thead><tr><th>Phiên</th><th>Mua CĐ</th><th>Bán CĐ</th><th>% mua</th><th>Ròng</th><th>ATO/ATC</th><th>Mua lớn</th><th>Bán lớn</th><th>Ròng lớn</th></tr></thead>
      <tbody>${body}${foot}</tbody></table></div>
      <div class="note">KL đơn vị cổ phiếu; cột lệnh lớn (≥ ${Math.round((Z.settings.big_lot_value_vnd || 5e8) / 1e6)} triệu đ/lệnh) đơn vị <b>tỷ đồng</b>, chỉ có ở phiên tick thật (${t.n_real || 0}/${t.n || rows.length} phiên). Mua bị động = bán chủ động và ngược lại, nên hai cột mua/bán chủ động là đủ. Phiên "ước lượng" dựng từ nến 1 phút, mua/bán chỉ đoán theo hướng nến, tô nhạt.${rows.some((r) => r.no_side) ? " Phiên \"không có bên CĐ\": VNDirect không ghi bên chủ động cho mã này, cả phiên nằm ở cột ATO/ATC — không tính được mua/bán." : ""}</div>`;
  }

  function renderMarket() {
    const el = $("z-mkt");
    const M = (Z && Z.market) || {};
    const list = Object.entries(M).map(([k, r]) => ({ k, r, w: r.w5 || {} }));
    list.sort((a, b) => zmsort === "big" ? (b.r.big_net_val ?? -1e9) - (a.r.big_net_val ?? -1e9)
      : zmsort === "sell" ? (a.r.net_pct ?? 9) - (b.r.net_pct ?? 9) : (b.r.net_pct ?? -9) - (a.r.net_pct ?? -9));
    document.querySelectorAll("#z-msort button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.ms === zmsort ? "true" : "false"));
    if (!list.length) { el.innerHTML = `<h4>Toàn danh mục <span class="n">— chưa có dữ liệu</span></h4>`; return; }
    const w5pct = (w) => (w.buy + w.sell ? w.net / (w.buy + w.sell) : null);
    const rows = list.map(({ k, r, w }) => `<tr data-zsym="${esc(k)}"><td>${esc(k)}${r.est ? '<span class="est">ước lượng</span>' : ""}${r.no_side ? '<span class="est">nguồn không ghi bên CĐ</span>' : ""}</td>` +
      `<td class="share ${r.buy_share >= 0.5 ? "up" : "down"}"><b>${pct(r.buy_share)}</b></td>` +
      `<td class="${cls(r.net_pct)}">${r.net_pct == null ? "—" : sgn(r.net_pct) + Math.abs(Math.round(r.net_pct * 100)) + " %"}</td>` +
      `<td class="${cls(r.big_net_val)}">${sbil(r.big_net_val)}</td>` +
      `<td class="${cls(w.net)}">${w5pct(w) == null ? "—" : sgn(w.net) + Math.abs(Math.round(w5pct(w) * 100)) + " %"}</td>` +
      `<td class="${cls(w.big_net_val)}">${sbil(w.big_net_val)}</td></tr>`).join("");
    el.innerHTML = `<h4>Toàn danh mục — phiên ${dmy(Z.trade_date)} <span class="n">— bấm một mã để xem chi tiết</span></h4>
      <table class="wide mkt"><thead><tr><th>Mã</th><th>% mua</th><th>Ròng</th><th>Ròng lớn</th><th>Ròng 5p</th><th>Lớn 5p</th></tr></thead><tbody>${rows}</tbody></table>
      <div class="note"><b>% mua</b> = mua chủ động / (mua + bán chủ động). <b>Ròng</b> = (mua − bán chủ động) / (mua + bán chủ động). <b>Ròng lớn</b> = giá trị lệnh ≥ ${Math.round((Z.settings.big_lot_value_vnd || 5e8) / 1e6)} triệu đ mua chủ động trừ bán chủ động, <b>tỷ đồng</b>. Cột 5p cộng 5 phiên gần nhất. Thống kê mô tả — đã đo 23/09: KL × thân nến không cho biết hướng giá phiên sau.</div>`;
  }

  function showZoneMode() {
    document.querySelectorAll("#z-mode button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.mode === zmode ? "true" : "false"));
    $("z-mktview").hidden = zmode !== "mkt";
    $("z-symview").hidden = zmode !== "sym";
  }
  $("z-mode").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-mode]"); if (!b) return;
    zmode = b.dataset.mode; renderZone();
  });
  $("z-msort").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-ms]"); if (!b) return;
    zmsort = b.dataset.ms; renderMarket();
  });
  $("z-mkt").addEventListener("click", (ev) => {
    const tr = ev.target.closest("tr[data-zsym]"); if (!tr) return;
    zcur = tr.dataset.zsym; $("z-sym").value = zcur; zmode = "sym"; renderZone();
    window.scrollTo(0, 0);
  });

  async function renderZone() {
    if (!Z) await loadZone();
    showZoneMode();
    if (zmode === "mkt") { $("zoneKicker").textContent = Z ? `phiên ${dmy(Z.trade_date)}` : "—"; renderMarket(); return; }
    const s = zsym();
    if (!s) return;
    const p = s.profiles[zwin] || s.profiles["40"];
    $("zoneKicker").textContent = `phiên ${dmy(Z.trade_date)}`;
    $("z-px").textContent = px(s.price);
    document.querySelectorAll("#z-win button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.win === zwin ? "true" : "false"));
    $("z-big").className = "tg " + (zbig ? "on" : "off");
    $("z-big-note").textContent = `Lệnh ≥ ${Math.round((Z.settings.big_lot_value_vnd || 5e8) / 1e6)} triệu đ · chỉ có ở ${s.real_sessions} phiên tick thật`;
    if (!p) { $("z-prof").innerHTML = `<div class="empty">Chưa có dữ liệu cho mã này.</div>`; return; }
    const estN = p.n - p.n_real;
    const fac = p.factors ? ` · ${p.factors} phiên đã quy về thang giá điều chỉnh` : "";
    $("z-strip").className = "strip" + (p.n_real < p.n / 2 ? " pending" : "");
    $("z-strip").innerHTML = `<b>${p.n_real}/${p.n} phiên là tick thật</b> (${dmy(p.from)} → ${dmy(p.to)})${estN ? `; ${estN} phiên còn lại dựng từ nến 1 phút — KL theo giá đúng, <b>mua/bán chỉ ước lượng</b> theo hướng nến, tô nhạt` : ""}${fac}. Mua ${pct(p.buy / (p.buy + p.sell || 1))} · ATO/ATC ${pct(p.x / (p.total || 1))} · tổng KL ${vol(p.total)}.`;
    $("z-prof").innerHTML = profileChart(p, s.price, 358, zbig);
    renderFlow(s, p);
    const top = p.top || {};
    topTable("z-topb", zbig ? "Giá cá mập mua CĐ nhiều nhất" : "Giá mua chủ động nhiều nhất", zbig ? top.big_buy : top.buy, "mua");
    topTable("z-tops", zbig ? "Giá cá mập bán CĐ nhiều nhất" : "Giá bán chủ động nhiều nhất", zbig ? top.big_sell : top.sell, "bán");
    if (zbig) {
      zoneTable("z-buy", "Cá mập mua nhiều", p.big_buy_zones, "up");
      zoneTable("z-sell", "Cá mập bán nhiều", p.big_sell_zones, "down");
    } else {
      zoneTable("z-buy", "Vùng mua nhiều", p.buy_zones, "up");
      zoneTable("z-sell", "Vùng bán nhiều", p.sell_zones, "down");
    }
    const st = Z.settings;
    $("z-why").innerHTML = `<h4>Cách đọc</h4>
      <p>Mỗi hàng là một ô giá rộng ${px(p.bin)}; thanh dài = nhiều cổ phiếu đã đổi chủ ở giá đó trong ${p.n} phiên. <b>POC</b> là ô nhiều nhất, <b>Value Area</b> là dải chứa 70 % KL — nơi phần lớn cổ phiếu đã đổi chủ; <b>VAH / VAL</b> là biên trên / biên dưới của dải. Đã đo 10 năm trên 39 mã: VAH/VAL không giữ hay cản giá tốt hơn một mức bất kỳ — chỉ dùng làm bản đồ. Xanh/đỏ = bên chủ động: mua chủ động là lệnh mua đập vào giá bán đang chờ, bán chủ động ngược lại; ATO/ATC không có bên chủ động. Mỗi cổ phiếu khớp có một bên chủ động và một bên bị động, nên <b>mua bị động = bán chủ động</b>.</p>
      <p><b>Vùng mua nhiều</b> = các ô liền nhau có KL ≥ ${st.zone_vol_mult}× trung bình ô và ≥ ${Math.round(st.buy_share_min * 100)} % mua chủ động; <b>vùng bán nhiều</b> ≤ ${Math.round(st.sell_share_max * 100)} % mua. Vùng mua dưới giá hiện tại thường là chỗ có người đỡ; vùng bán trên giá là chỗ hàng chờ ra.</p>
      <p><b>Giá mua / bán chủ động nhiều nhất</b> xếp theo từng mức giá khớp chính xác (không gộp ô), cộng cả ${p.n} phiên; giá cũ đã quy về thang điều chỉnh rồi làm tròn về bước giá. <b>% tổng</b> = phần của mức đó trong toàn bộ mua (bán) chủ động của khung. Mức có nhãn "ước lượng" phần lớn KL đến từ phiên dựng bằng nến 1', mua/bán chỉ đoán — chọn khung 10 phiên để xem gần như toàn tick thật.</p>
      <p class="warn">Tick thật chỉ gom được mỗi ngày một phiên từ 18/09/2026; phần ước lượng từ nến 1' được thay dần. Chưa đo được vùng có giá trị dự báo hay không — đây là thống kê mô tả, không phải khuyến nghị.</p>`;
  }
  $("z-sym").addEventListener("change", () => { zcur = $("z-sym").value; renderZone(); });
  $("z-win").addEventListener("click", (ev) => { const b = ev.target.closest("button[data-win]"); if (!b) return; zwin = b.dataset.win; try { localStorage.setItem("pp_zwin", zwin); } catch (_) {} renderZone(); });
  $("z-big").addEventListener("click", () => { zbig = !zbig; renderZone(); });

  // ---------------------------------------------------------------- Sổ chấm
  function renderEventLog() {
    const log = D.event_log || [], el = $("histEv");
    if (!evMeta().enabled || !evMeta().enabled.length) { el.hidden = true; return; }
    el.hidden = false;
    const done = log.filter((e) => e.ret10 != null), live = done.filter((e) => e.live && e.in80 != null);
    const avg = done.length ? done.reduce((a, e) => a + e.ret10, 0) / done.length : null;
    const up = done.filter((e) => e.ret10 > 0).length;
    const res = (e) => (e.ret10 != null ? `<b style="color:${e.ret10 >= 0 ? UP : DOWN}">${spc(e.ret10)}</b>` : `<span style="color:${MUTE}">đang: ${spc(e.ret_now)} · ${e.age} phiên</span>`);
    const cone = (e) => (!e.live ? `<span style="color:${MUTE}">—</span>` : e.in80 == null ? `<span style="color:${MUTE}">chờ</span>` : e.in80 ? `<span style="color:${UP};font-weight:700">✓</span>` : `<span style="color:${DOWN};font-weight:700">✗</span>`);
    const rows = log.slice(0, 20).map((e) => `<tr><td>${dmy(e.date)}<span class="z">${e.date.slice(0, 4)}</span></td><td class="l"><b>${esc(e.symbol)}</b><span class="z">${esc(e.event)}</span></td><td>${res(e)}</td><td class="c">${cone(e)}</td></tr>`);
    el.innerHTML = `<h4>Nhật ký sự kiện · 1 năm gần nhất <span class="n">— ${log.length} lần${log.length > 20 ? ", hiện 20 gần nhất" : ""}</span></h4>
      <div class="evsum"><div><span class="k">Đủ 10 phiên</span><span class="v">${done.length}</span></div><div><span class="k">Lãi TB 10p</span><span class="v">${spc(avg)}</span></div><div><span class="k">Số lần tăng</span><span class="v">${done.length ? `${up}/${done.length}` : "—"}</span></div><div><span class="k">Trong nón 80 %</span><span class="v">${live.length ? `${live.filter((e) => e.in80).length}/${live.length}` : "—"}</span></div></div>
      <table><thead><tr><th>Ngày</th><th style="text-align:left">Mã · sự kiện</th><th>+10 phiên</th><th style="text-align:center">Nón 80 %</th></tr></thead><tbody>${rows.join("") || `<tr><td colspan="4">Chưa có sự kiện nào trong 1 năm.</td></tr>`}</tbody></table>
      <div class="note">Lãi = giá đóng cửa sau 10 phiên so với ngày sự kiện, chưa trừ phí, chưa so thị trường. Cột Nón chỉ chấm sự kiện app đã phát thật (từ 24/09/2026); sự kiện trước đó dựng lại từ lịch sử nên ghi "—".</div>`;
  }

  function renderHistory() {
    renderEventLog();
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
      const em = evMeta(), en = em.enabled || [], pu = em.push || [];
      const evRows = Object.entries(em.stats || {}).map(([k, v]) => `<tr><td>${esc(v.name)}</td><td>${spc(v.ex10)}</td><td>${v.years_win}/${v.years}</td><td>${v.scale ? Number(v.scale["80"]).toFixed(2) : "—"}</td><td class="c">${!v.pass ? `<span style="color:${MUTE}">trượt</span>` : pu.includes(k) ? `<span class="pill on">push</span>` : en.includes(k) ? `<span class="pill n">chỉ hiện</span>` : `<span class="pill off">tắt</span>`}</td></tr>`).join("");
      $("pushHelp").innerHTML = evMode()
        ? `Sau phiên 15:40 T2–T6, app báo khi một mã dính sự kiện đang bật push (${esc(pu.map((k) => (em.stats[k] && em.stats[k].name) || k).join(", ") || "không có")}). Sự kiện "chỉ hiện" đã có app khác báo (SC → Wyckoff Radar) nên chỉ hiện trên app. Quá ${s.digest_threshold} mã → một thông báo gộp.`
        : `Sau phiên 15:40 T2–T6, app chỉ báo mã có P(tăng 10p) qua ngưỡng và ô chế độ đủ mẫu. Quá ${s.digest_threshold} mã → một thông báo gộp.`;
      $("thresholds").innerHTML = `<div class="l"><span>Chế độ chuông</span><span class="pill ${evMode() ? "on" : "n"}">${evMode() ? "theo sự kiện" : "P(tăng) cũ"}</span></div>
        <div class="tbl" style="margin:6px 0 4px;padding:6px 0 0"><table><thead><tr><th>Sự kiện</th><th>Vượt 10p</th><th>Năm</th><th>Nới 80 %</th><th style="text-align:center">Trạng thái</th></tr></thead><tbody>${evRows}</tbody></table>
        <div class="note">Đo 2016–2026, cổng: ≥ 100 lần · ≥ 70 % số năm vượt mua-đại · bỏ 2022 vẫn dương · vượt ≥ 1 %/10p (reports/events-${esc(em.generated || "")}.md). "Nới 80 %" = hệ số giãn nón vì ngày có sự kiện biến động hơn thường.</div></div>
        <div class="l"><span>Ngưỡng P(tăng 10p) — chỉ khi chế độ cũ</span><span class="pill ${evMode() ? "off" : "n"}">≥ ${pct(s.p_min)}</span></div>
        <div class="l"><span>Gộp khi nhiều mã</span><span class="pill n">> ${s.digest_threshold} mã</span></div>
        <div class="l"><span>Nhịp tim thứ Hai</span><span class="pill ${s.heartbeat ? "on" : "off"}">${s.heartbeat ? "bật" : "tắt"}</span></div>
        <div class="h">Đổi sự kiện push / bật lại chế độ cũ: sửa <span class="mono">events_push</span>, <span class="mono">alert_mode</span> trong <span class="mono">docs/data/settings.json</span> rồi push — job chạy lại ngay.</div>`;
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
    // Hai state riêng: job daily (data/state.json) và job vùng giá (data/zone/state.json, zone.yml chạy độc
    // lập). Trước 23/09/2026 state của zone không được đọc ở đâu cả, nên job đỏ 3 lượt liền trong ngày mà
    // app im lặng — chỉ phát hiện được khi tình cờ mở tab Vùng giá và đọc chữ "phiên ..." nhỏ. Gộp một
    // Promise.all để hai lần fetch không ghi đè nhau trên cùng ô stateFoot.
    const getJSON = (u) => fetch(u, { cache: "no-cache" }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    Promise.all([getJSON("data/state.json"), getJSON("data/zone/state.json")]).then(([st, zs]) => {
      const rows = [];
      if (st) {
        const dv = st.devices || {}, p = st.push || {};
        let s = `Job chạy lần cuối ${st.last_run ? esc(st.last_run.slice(0, 16).replace("T", " ")) : "—"} · ${dv.n || 0} máy đã đăng ký (${esc(dv.source || "—")}) · VAPID ${dv.vapid ? "OK" : "THIẾU"}`;
        if (p.mode) s += ` · lần báo gần nhất: ${esc(p.mode)}, gửi ${p.sent || 0}`;
        if (p.errors && p.errors.length) s += ` · <b>${esc(p.errors[0])}</b>`;
        if (st.push_gone_at) s += ` · <b>có máy đã huỷ đăng ký (${esc(st.push_gone_at.slice(0, 10))}) — bấm Bật thông báo lại</b>`;
        rows.push(s);
      }
      if (zs) {
        // state.json của zone chỉ được ghi khi có phiên mới, nên ngày của ran_at cũ hơn phiên job daily
        // nghĩa là job vùng giá chưa chốt được phiên gần nhất — đúng dấu hiệu của sự cố 23/09/2026.
        const ran = (zs.ran_at || "").slice(0, 10);
        // D có thể còn null (khối này nằm ngoài guard ở trên, latest.json tải xong sau) — không so thì thôi.
        const behind = ran && D && D.trade_date && ran < D.trade_date;
        const nf = (zs.failed || []).length, nw = (zs.warnings || []).length;
        let z = `Job vùng giá ${ran ? esc(zs.ran_at.slice(0, 16).replace("T", " ")) : "—"}`;
        z += behind ? ` · <b style="color:${DOWN}">chậm: phiên gần nhất là ${dmy(D.trade_date)}</b>` : ` · ${zs.collected ? zs.collected.length : 0} mã`;
        if (nf) z += ` · <b style="color:${DOWN}">lỗi ${nf} mã: ${esc((zs.failed || []).slice(0, 5).join(", "))}</b>`;
        if (zs.vndirect_last_error) z += ` · <b style="color:${DOWN}">${esc(zs.vndirect_last_error)}</b>`;
        if (nw) z += ` · ${nw} cảnh báo: ${esc(zs.warnings[0])}`;
        rows.push(z);
      }
      $("stateFoot").innerHTML = rows.join("<br>");
    });
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
    if (name === "zone") renderZone();
  }
  tabs.forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));
  function applyHash() { const m = /^#(today|history|chart|zone|settings)$/.exec(location.hash); if (m) switchTab(m[1]); }
  window.addEventListener("hashchange", applyHash);
  if ("serviceWorker" in navigator) navigator.serviceWorker.register(SW).catch(() => {});
  load().then(() => { applyHash(); pushStatus(); });
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") { load(); if ($("p-zone").classList.contains("on")) { Z = null; renderZone(); } } });
})();
