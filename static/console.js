const reserve = document.querySelector("#reserve");
const cancel = document.querySelector("#cancel");
const stock = document.querySelector("#stock");
const statusLine = document.querySelector("[role=status]");
const entries = document.querySelector("#entries");
const payload = document.querySelector("#payload");
let pendingKey = sessionStorage.getItem("pendingReservation");
let receipt = sessionStorage.getItem("receipt");
let total = 0;

function record(method, path, status, details, failed) {
  const row = document.createElement("button");
  row.className = "entry";
  for (const [tag, value] of [["b", method], ["span", path], ["em", status]]) {
    const part = document.createElement(tag);
    part.textContent = value;
    if (tag === "em" && failed) part.className = "error";
    row.append(part);
  }
  row.setAttribute("aria-label", [method, path, status].join(" "));
  row.onclick = () => {
    const previous = entries.querySelector('[aria-pressed="true"]');
    if (previous) previous.setAttribute("aria-pressed", "false");
    row.setAttribute("aria-pressed", "true");
    payload.textContent = details;
  };
  entries.prepend(row);
  document.querySelector("#count").textContent = (++total) + " 笔";
  row.click();
}

async function send(path, options = {}) {
  const method = options.method || "GET";
  const lines = [method + " " + path];
  if (options.headers?.["Idempotency-Key"]) {
    lines.push("Idempotency-Key: " + options.headers["Idempotency-Key"]);
  }
  if (options.body) lines.push(options.body);
  let response;
  let data;
  try {
    response = await fetch(path, options);
    data = await response.json();
  } catch (error) {
    record(method, path, "未收到回执", lines.concat("未取得完整响应").join("\n"), true);
    throw error;
  }
  lines.push("HTTP " + response.status);
  if (response.headers.has("Location")) lines.push("Location: " + response.headers.get("Location"));
  lines.push(JSON.stringify(data, null, 2));
  record(method, path, response.status, lines.join("\n"), !response.ok);
  return {response, data};
}

function showStock(count) {
  stock.textContent = count;
  reserve.disabled = count === 0;
}

async function refresh() {
  const {response, data} = await send("/api/stock");
  if (!response.ok) throw new Error("stock");
  showStock(data.available);
}

function allowRetry() {
  statusLine.textContent = "未收到预约回执，请重试";
  reserve.textContent = "重试预约";
  reserve.disabled = false;
}

reserve.onclick = async () => {
  reserve.disabled = true;
  pendingKey ??= crypto.randomUUID();
  sessionStorage.setItem("pendingReservation", pendingKey);
  try {
    const {response, data} = await send("/api/reservations", {
      method: "POST",
      headers: {"Content-Type": "application/json", "Idempotency-Key": pendingKey},
      body: JSON.stringify({quantity: 1})
    });
    const dropReceipt = document.querySelector("#drop-receipt");
    if (response.ok && dropReceipt.checked) {
      dropReceipt.checked = false;
      allowRetry();
      return;
    }
    if (!response.ok && data.error !== "insufficient_stock") {
      allowRetry();
      return;
    }
    if (response.ok) {
      receipt = response.headers.get("Location");
      sessionStorage.setItem("receipt", receipt);
      cancel.hidden = false;
    }
    sessionStorage.removeItem("pendingReservation");
    pendingKey = null;
    reserve.textContent = "预约一台";
    showStock(data.available);
    statusLine.textContent = response.ok ? "预约成功" : "库存不足，请下次再来";
  } catch {
    allowRetry();
  }
};

cancel.onclick = async () => {
  cancel.disabled = true;
  try {
    const {response, data} = await send(receipt, {method: "DELETE"});
    if (!response.ok || data.state !== "cancelled") throw new Error("cancel");
    cancel.hidden = true;
    sessionStorage.removeItem("receipt");
    receipt = null;
    statusLine.textContent = "预约已取消";
    await refresh();
  } catch {
    statusLine.textContent = receipt ? "未确认取消结果，请再次取消" : "库存读取失败，请刷新";
  } finally {
    cancel.disabled = false;
  }
};

async function openDesk() {
  if (pendingKey) {
    allowRetry();
    return;
  }
  if (receipt) {
    const {response, data} = await send(receipt);
    if (response.ok && data.state === "active") cancel.hidden = false;
    else if (response.ok || response.status === 404) {
      sessionStorage.removeItem("receipt");
      receipt = null;
    }
  }
  await refresh();
}

openDesk().catch(() => { statusLine.textContent = "读取失败，请刷新页面"; });
