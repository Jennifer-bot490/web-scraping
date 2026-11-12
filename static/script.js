const form = document.getElementById("scan-form");
const goBtn = document.getElementById("go");
const statusEl = document.getElementById("status");
const results = document.getElementById("results");
const panel = document.getElementById("panel");
const tabs = document.querySelectorAll(".tabs button");
let report = null;
let activeTab = "overview";

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const link = (u, label) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(label || u)}</a>`;

function setStatus(msg, type = "") {
  statusEl.textContent = msg;
  statusEl.className = type;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  goBtn.disabled = true;
  results.hidden = true;
  setStatus("Scanning pages. This can take up to a minute.", "busy");
  try {
    const res = await fetch("/api/scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: document.getElementById("url").value,
        max_pages: Number(document.getElementById("max").value),
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Something went wrong.");
    report = data;
    showReport();
    setStatus(`Scanned ${data.pages.length} page${data.pages.length === 1 ? "" : "s"}.`);
  } catch (err) {
    setStatus(err.message || "Could not reach the backend. Is app.py running?", "error");
  } finally {
    goBtn.disabled = false;
  }
});

function showReport() {
  const { site, pages, services, contact } = report;
  document.getElementById("site-title").textContent = site.title || site.domain;
  const a = document.getElementById("site-link");
  a.textContent = site.url;
  a.href = site.url;
  document.getElementById("n-pages").textContent = pages.length;
  document.getElementById("n-services").textContent = services.length;
  document.getElementById("n-contact").textContent =
    contact.emails.length + contact.phones.length + contact.socials.length + contact.addresses.length;
  results.hidden = false;
  selectTab("overview");
}

function selectTab(name) {
  activeTab = name;
  tabs.forEach((t) => t.setAttribute("aria-selected", String(t.dataset.tab === name)));
  panel.innerHTML = views[name]();
}
tabs.forEach((t) => t.addEventListener("click", () => selectTab(t.dataset.tab)));

const list = (title, items, render = esc) =>
  `<div class="group"><h3>${title}</h3>${
    items.length ? `<ul>${items.map((i) => `<li>${render(i)}</li>`).join("")}</ul>` : `<p class="empty">None found.</p>`
  }</div>`;

const views = {
  overview() {
    const s = report.site;
    return `
      <div class="group"><h3>What this website is for</h3>
        <p>${s.purpose ? esc(s.purpose) : '<span class="empty">No description found on the home page.</span>'}</p></div>
      ${s.about ? `<div class="group"><h3>From the about page</h3><p>${esc(s.about)}</p></div>` : ""}`;
  },
  pages() {
    return report.pages
      .map(
        (p) => `<div class="item">
          <h3>${esc(p.title || "Untitled page")}</h3>
          ${link(p.url)}
          ${p.description ? `<p class="muted">${esc(p.description)}</p>` : ""}
          <div class="tags">${p.headings.slice(0, 6).map((h) => `<span>${esc(h)}</span>`).join("")}</div>
          <div class="muted">${p.words} words</div>
        </div>`
      )
      .join("");
  },
  services() {
    if (!report.services.length)
      return `<p class="empty">No service or product pages were found. Try scanning more pages.</p>`;
    return report.services
      .map(
        (s) => `<div class="item">
          <h3>${esc(s.name)}</h3>
          ${link(s.url)}
          ${s.description ? `<p class="muted">${esc(s.description)}</p>` : ""}
          <div class="tags">${s.details.map((d) => `<span>${esc(d)}</span>`).join("")}</div>
        </div>`
      )
      .join("");
  },
  contact() {
    const c = report.contact;
    return (
      list("Email", c.emails, (e) => link("mailto:" + e, e)) +
      list("Phone", c.phones) +
      list("Address", c.addresses) +
      list("Social media", c.socials, (u) => link(u)) +
      list("Contact pages", c.pages, (u) => link(u))
    );
  },
};

document.getElementById("download").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${report.site.domain}-report.json`;
  a.click();
  URL.revokeObjectURL(a.href);
});
