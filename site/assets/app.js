"use strict";

const siteData = JSON.parse(document.querySelector("#site-data").textContent);
const messages = siteData.messages;

// Keep language links on the corresponding document and translated section.
function updateLanguageLinks() {
  let fragment;
  try { fragment = decodeURIComponent(window.location.hash.slice(1)); }
  catch { fragment = ""; }
  document.querySelectorAll("[data-language]").forEach((link) => {
    const target = new URL(link.href);
    target.hash = link.dataset.language === document.documentElement.lang
      ? fragment : siteData.fragments[fragment] || fragment;
    link.href = target.href;
  });
}
updateLanguageLinks();
window.addEventListener("hashchange", updateLanguageLinks);

// The document, navigation and source links remain usable without JavaScript.
const sidebar = document.querySelector(".sidebar details");
if (sidebar) {
  const mobile = window.matchMedia("(max-width: 760px)");
  const update = () => { sidebar.open = !mobile.matches; };
  mobile.addEventListener("change", update);
  update();
}

if (navigator.clipboard && window.isSecureContext) {
  document.querySelectorAll(".highlight, .install-bar pre").forEach((block) => {
    const code = block.querySelector("pre") || block.querySelector("code");
    if (!code) return;
    const source = code.textContent;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "copy-code";
    button.textContent = messages.copy;
    button.setAttribute("aria-label", messages.copy_label);
    button.setAttribute("aria-live", "polite");
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(source);
        button.textContent = messages.copied;
      } catch {
        button.textContent = messages.copy_error;
      }
      window.setTimeout(() => { button.textContent = messages.copy; }, 2000);
    });
    block.append(button);
  });
}

const toc = [...document.querySelectorAll(".page-toc a[href^='#']")];
if (toc.length && "IntersectionObserver" in window) {
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      toc.forEach((link) => {
        if (decodeURIComponent(link.hash.slice(1)) === entry.target.id) {
          link.setAttribute("aria-current", "location");
        } else {
          link.removeAttribute("aria-current");
        }
      });
    }
  }, { rootMargin: "-5% 0px -65% 0px" });
  document.querySelectorAll(".prose h2, .prose h3").forEach((heading) => observer.observe(heading));
}

const dialog = document.querySelector(".search-dialog");
const trigger = document.querySelector(".search-trigger");
const input = document.querySelector("#search-input");
const results = document.querySelector(".search-results");
const status = document.querySelector(".search-status");
let indexPromise;
let searchGeneration = 0;
const indexURL = new URL(document.documentElement.dataset.searchIndex, document.baseURI);
const siteBase = new URL("./", indexURL);

async function loadIndex() {
  if (!indexPromise) {
    indexPromise = fetch(indexURL).then((response) => {
      if (!response.ok) throw new Error("Search index unavailable");
      return response.json();
    }).catch((error) => {
      indexPromise = undefined; // A later search can retry after a transient failure.
      throw error;
    });
  }
  return indexPromise;
}

async function search() {
  const generation = ++searchGeneration;
  const query = input.value.trim().toLocaleLowerCase();
  results.replaceChildren();
  if (!query) {
    status.textContent = messages.search_empty;
    return;
  }
  status.textContent = messages.search_loading;
  try {
    const index = await loadIndex();
    if (generation !== searchGeneration) return;
    const terms = query.split(/\s+/).slice(0, 12);
    const matches = index.map((entry) => {
      const title = entry.title.toLocaleLowerCase();
      const text = entry.text.toLocaleLowerCase();
      const combined = `${entry.page.toLocaleLowerCase()} ${title} ${text}`;
      const score = terms.every((term) => combined.includes(term))
        ? terms.reduce((sum, term) => sum + (title.includes(term) ? 15 : 0) + (text.includes(term) ? 1 : 0), 0)
        : 0;
      return { entry, score };
    }).filter(({ score }) => score > 0).sort((a, b) => b.score - a.score);
    status.textContent = matches.length
      ? messages.search_matches.replace("{count}", matches.length) + (matches.length > 30 ? messages.search_limit : "")
      : messages.search_no_matches;
    for (const { entry } of matches.slice(0, 30)) {
      const item = document.createElement("li");
      const link = document.createElement("a");
      link.href = new URL(entry.url, siteBase).href;
      const page = document.createElement("small");
      page.textContent = entry.page;
      const title = document.createElement("strong");
      title.textContent = entry.title;
      const snippet = document.createElement("p");
      const first = entry.text.toLocaleLowerCase().indexOf(terms[0]);
      const start = Math.max(0, first - 35);
      snippet.textContent = `${start ? "…" : ""}${entry.text.slice(start, start + 150)}${entry.text.length > start + 150 ? "…" : ""}`;
      link.append(page, title, snippet);
      link.addEventListener("click", () => dialog.close());
      item.append(link);
      results.append(item);
    }
  } catch {
    if (generation === searchGeneration) status.textContent = messages.search_error;
  }
}

if (dialog && typeof dialog.showModal === "function") {
  trigger.hidden = false;
  trigger.querySelector("kbd").textContent = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘ K" : "Ctrl K";
  const open = () => {
    if (!dialog.open) dialog.showModal();
    input.focus();
    search();
  };
  trigger.addEventListener("click", open);
  input.addEventListener("input", search);
  dialog.addEventListener("click", (event) => {
    const rect = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
  });
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      if (dialog.open) dialog.close(); else open();
    }
  });
  dialog.addEventListener("keydown", (event) => {
    const links = [...results.querySelectorAll("a")];
    const current = links.indexOf(document.activeElement);
    if (event.key === "ArrowDown" && links.length) {
      event.preventDefault();
      links[(current + 1) % links.length].focus();
    } else if (event.key === "ArrowUp" && links.length) {
      event.preventDefault();
      if (current <= 0) input.focus(); else links[current - 1].focus();
    } else if (event.key === "Enter" && document.activeElement === input && links.length) {
      event.preventDefault();
      links[0].click();
    }
  });
}
