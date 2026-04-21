/* ─── Telegram WebApp init ─────────────────────────────────── */
const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

const INIT_DATA = tg?.initData || "";

/* ─── State ────────────────────────────────────────────────── */
const state = {
  tab: "dashboard",
  paused: false,
  simulated: true,
  settings: {},
  positions: [],
  orders: [],
  refreshTimer: null,
};

/* ─── API helpers ──────────────────────────────────────────── */
async function api(method, path, body) {
  const opts = {
    method: method || "GET",
    headers: { "x-telegram-init-data": INIT_DATA },
  };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

const GET  = (path)        => api("GET",  path);
const POST = (path, body)  => api("POST", path, body);

/* ─── Toast ────────────────────────────────────────────────── */
let toastEl;
function showToast(msg) {
  if (!toastEl) {
    toastEl = document.createElement("div");
    toastEl.className = "toast";
    document.body.appendChild(toastEl);
  }
  toastEl.textContent = msg;
  toastEl.classList.add("show");
  clearTimeout(toastEl._t);
  toastEl._t = setTimeout(() => toastEl.classList.remove("show"), 2500);
}

/* ─── Tab navigation ───────────────────────────────────────── */
function switchTab(tab) {
  state.tab = tab;
  document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
  document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
  document.getElementById("screen-" + tab).classList.add("active");
  document.getElementById("nav-" + tab).classList.add("active");
  refreshCurrentTab();
}

/* ─── Refresh ──────────────────────────────────────────────── */
document.getElementById("refresh-btn").addEventListener("click", () => {
  loadAll();
  if (tg) tg.HapticFeedback?.impactOccurred("light");
});

async function loadAll() {
  try {
    const [statusData, targetData] = await Promise.all([
      GET("/api/status"),
      GET("/api/target").catch(() => ({})),
    ]);
    applyStatus(statusData);
    applyTarget(targetData);
  } catch (e) {
    console.error("loadAll error:", e);
  }
  refreshCurrentTab();
}

function refreshCurrentTab() {
  const tab = state.tab;
  if (tab === "positions") loadPositions();
  else if (tab === "orders") loadOrders();
  else if (tab === "settings") loadSettings();
}

/* ─── Status ───────────────────────────────────────────────── */
function applyStatus(data) {
  state.paused    = data.paused ?? false;
  state.simulated = data.simulated ?? true;

  // Status badge
  const sb = document.getElementById("status-badge");
  if (state.paused) {
    sb.textContent = "PAUSED";
    sb.className = "badge badge-paused";
  } else {
    sb.textContent = "ACTIVE";
    sb.className = "badge badge-active";
  }

  // Mode badge
  const mb = document.getElementById("mode-badge");
  if (state.simulated) {
    mb.textContent = "SIM";
    mb.className = "badge badge-sim";
  } else {
    mb.textContent = "LIVE";
    mb.className = "badge badge-live";
  }

  // Pause button
  const pb = document.getElementById("pause-btn");
  if (state.paused) {
    pb.textContent = "▶ Resume Bot";
    pb.className = "btn btn-resume";
  } else {
    pb.textContent = "⏸ Pause Bot";
    pb.className = "btn btn-pause";
  }

  // Parse balance/pnl/positions/trades from status text
  if (data.text) {
    const balMatch  = data.text.match(/Balance[^\$]*\$([\d,\.]+)/);
    const pnlMatch  = data.text.match(/PnL[^\$]*\$([-\d,\.]+)/);
    const posMatch  = data.text.match(/Open Positions.*?(\d+)/);
    const trdMatch  = data.text.match(/Trades Copied.*?(\d+)/);

    if (balMatch)  document.getElementById("dash-balance").textContent  = "$" + balMatch[1];
    if (trdMatch)  document.getElementById("dash-trades").textContent   = trdMatch[1];
    if (posMatch)  document.getElementById("dash-positions").textContent = posMatch[1];

    if (pnlMatch) {
      const val  = parseFloat(pnlMatch[1].replace(/,/g, ""));
      const el   = document.getElementById("dash-pnl");
      const sign = val >= 0 ? "+" : "";
      el.textContent = sign + "$" + Math.abs(val).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
      el.className = "card-value " + (val >= 0 ? "positive" : "negative");
    }
  }
}

/* ─── Target wallet ────────────────────────────────────────── */
function applyTarget(data) {
  if (!data || !data.address) return;
  const addr = data.address;
  document.getElementById("target-addr").textContent =
    addr.slice(0, 10) + "..." + addr.slice(-6);

  const fmt = n => "$" + (n ?? 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
  document.getElementById("target-balance").textContent   = fmt(data.balance);
  document.getElementById("target-positions").textContent = data.position_count ?? 0;
  const pnl = data.unrealized_pnl ?? 0;
  const pnlEl = document.getElementById("target-pnl");
  pnlEl.textContent = (pnl >= 0 ? "+" : "") + fmt(pnl);
  pnlEl.style.color = pnl >= 0 ? "var(--green)" : "var(--red)";
}

/* ─── Positions ────────────────────────────────────────────── */
async function loadPositions() {
  const container = document.getElementById("positions-list");
  try {
    const data = await GET("/api/positions");
    state.positions = data.positions || [];
    renderPositions(container);
  } catch (e) {
    container.innerHTML = `<div class="empty-state">❌ ${e.message}</div>`;
  }
}

function renderPositions(container) {
  if (!state.positions.length) {
    container.innerHTML = '<div class="empty-state">No open positions</div>';
    return;
  }
  container.innerHTML = state.positions.map(pos => {
    const side      = (pos.side || "LONG").toUpperCase();
    const sideClass = side === "LONG" ? "long" : "short";
    const pnl       = pos.unrealized_pnl ?? 0;
    const pnlSign   = pnl >= 0 ? "+" : "";
    const pnlClass  = pnl >= 0 ? "positive" : "negative";
    const pnlPct    = pos.entry_price
      ? ((pos.current_price - pos.entry_price) / pos.entry_price * 100 * (side === "LONG" ? 1 : -1))
      : 0;
    const fmt2 = n => (n ?? 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    return `
      <div class="pos-card">
        <div class="pos-header">
          <span class="pos-symbol">${pos.symbol}</span>
          <span class="pos-side ${sideClass}">${side} ${pos.leverage ?? 1}x</span>
        </div>
        <div class="pos-stats">
          <span>Entry <strong>$${fmt2(pos.entry_price)}</strong></span>
          <span>Now <strong>$${fmt2(pos.current_price)}</strong></span>
          <span>Size <strong>${Math.abs(pos.size ?? 0).toFixed(4)}</strong></span>
          <span>Notional <strong>$${fmt2(Math.abs(pos.size ?? 0) * (pos.current_price ?? 0))}</strong></span>
        </div>
        <div class="pos-pnl ${pnlClass}">
          ${pnlSign}$${fmt2(Math.abs(pnl))} (${pnlSign}${pnlPct.toFixed(2)}%)
        </div>
        <button class="close-btn" onclick="closePosition('${pos.symbol}')">
          ❌ Close ${pos.symbol}
        </button>
      </div>`;
  }).join("");
}

async function closePosition(symbol) {
  if (!confirm(`Close ${symbol} position?`)) return;
  try {
    showToast(`Closing ${symbol}…`);
    const res = await POST(`/api/positions/${symbol}/close`);
    showToast(res.ok ? `✅ ${symbol} closed` : `❌ Failed to close ${symbol}`);
    if (tg) tg.HapticFeedback?.notificationOccurred(res.ok ? "success" : "error");
    setTimeout(loadPositions, 1500);
  } catch (e) {
    showToast("❌ " + e.message);
  }
}

/* ─── Orders ───────────────────────────────────────────────── */
async function loadOrders() {
  const container = document.getElementById("orders-list");
  try {
    const data = await GET("/api/orders");
    const orders = data.orders || [];
    if (!orders.length) {
      container.innerHTML = '<div class="empty-state">No open orders</div>';
      return;
    }
    const fmt2 = n => (n ?? 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    container.innerHTML = orders.map(o => {
      const side      = String(o.side || "BUY").toUpperCase();
      const sideClass = side === "BUY" ? "buy" : "sell";
      const type      = String(o.order_type || "LIMIT").toUpperCase();
      return `
        <div class="order-card">
          <div class="order-left">
            <div class="order-symbol">
              ${o.symbol}
              <span class="order-side-badge ${sideClass}">${side}</span>
            </div>
            <div class="order-meta">${type}</div>
          </div>
          <div class="order-right">
            <div class="order-price">$${fmt2(o.price)}</div>
            <div class="order-size">${Math.abs(o.size ?? 0).toFixed(4)}</div>
          </div>
        </div>`;
    }).join("");
  } catch (e) {
    container.innerHTML = `<div class="empty-state">❌ ${e.message}</div>`;
  }
}

/* ─── Settings ─────────────────────────────────────────────── */
async function loadSettings() {
  try {
    const data = await GET("/api/settings");
    state.settings = data;
    renderSettings(data);
  } catch (e) {
    showToast("❌ " + e.message);
  }
}

function renderSettings(data) {
  const lev       = data.leverage_ratio ?? 1.0;
  const maxTrades = data.max_trades;
  const blocked   = data.blocked_assets || [];
  const simMode   = data.simulated_trading ?? true;

  document.getElementById("lev-val").textContent       = round1(lev) + "x";
  document.getElementById("max-trades-val").textContent = maxTrades == null ? "∞" : maxTrades;
  document.getElementById("mode-label").textContent    = simMode ? "Simulated" : "LIVE";

  const toggle = document.getElementById("mode-toggle");
  // toggle ON = LIVE (dangerous), toggle OFF = sim
  if (!simMode) toggle.classList.add("on"); else toggle.classList.remove("on");
  document.getElementById("mode-warning").style.display = simMode ? "none" : "block";

  const chips = document.getElementById("blocked-chips");
  chips.innerHTML = blocked.map(asset => `
    <div class="chip">
      ${asset}
      <button class="chip-remove" onclick="removeBlockedAsset('${asset}')">×</button>
    </div>`).join("");
}

async function saveSetting(key, value) {
  try {
    const res = await POST("/api/settings", { key, value });
    showToast(res.ok ? "✅ " + res.message : "❌ " + res.message);
    await loadSettings();
  } catch (e) {
    showToast("❌ " + e.message);
  }
}

function round1(n) { return Math.round(n * 10) / 10; }

async function adjustLeverage(delta) {
  const current = round1(state.settings.leverage_ratio ?? 1.0);
  const next    = round1(current + delta);
  if (next < 0.1 || next > 3.0) { showToast("Range: 0.1 – 3.0"); return; }
  await saveSetting("leverage_ratio", next);
}

async function adjustMaxTrades(delta) {
  const current = state.settings.max_trades;
  const next    = (current == null ? 0 : current) + delta;
  if (next < 1) { showToast("Minimum 1"); return; }
  await saveSetting("max_trades", next);
}

async function setMaxTradesUnlimited() {
  await saveSetting("max_trades", null);
}

async function addBlockedAsset() {
  const input = document.getElementById("blocked-input");
  const asset = input.value.trim().toUpperCase();
  if (!asset) { showToast("Enter an asset symbol"); return; }
  input.value = "";
  await saveSetting("blocked_add", asset);
}

async function removeBlockedAsset(asset) {
  await saveSetting("blocked_remove", asset);
}

async function toggleMode() {
  const simMode = state.settings.simulated_trading ?? true;
  if (simMode) {
    // Switching to LIVE — confirm
    if (!confirm("⚠️ Switch to LIVE trading? Real funds will be used!")) return;
  }
  await saveSetting("sim_mode", null);
  await loadAll(); // refresh badges too
}

/* ─── Pause / Resume ────────────────────────────────────────── */
async function togglePause() {
  try {
    if (state.paused) {
      await POST("/api/resume");
      showToast("▶ Bot resumed");
    } else {
      await POST("/api/pause");
      showToast("⏸ Bot paused");
    }
    if (tg) tg.HapticFeedback?.impactOccurred("medium");
    setTimeout(loadAll, 500);
  } catch (e) {
    showToast("❌ " + e.message);
  }
}

/* ─── Auto-refresh (every 30 s) ─────────────────────────────── */
function startAutoRefresh() {
  clearInterval(state.refreshTimer);
  state.refreshTimer = setInterval(loadAll, 30000);
}

/* ─── Boot ──────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
  loadAll();
  startAutoRefresh();
});
