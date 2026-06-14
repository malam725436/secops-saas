// Confirm before destructive actions (e.g. removing a roster entry).
document.addEventListener("submit", (event) => {
  const form = event.target;
  const message = form.getAttribute("data-confirm");
  if (message && !window.confirm(message)) {
    event.preventDefault();
  }
});

// Light/dark theme toggle, persisted in localStorage.
const themeToggle = document.getElementById("theme-toggle");
if (themeToggle) {
  const root = document.documentElement;

  const syncToggle = (theme) => {
    const switchingTo = theme === "dark" ? "light" : "dark";
    themeToggle.setAttribute("aria-pressed", String(theme === "dark"));
    themeToggle.setAttribute("aria-label", `Switch to ${switchingTo} mode`);
  };

  syncToggle(root.getAttribute("data-theme") || "light");

  themeToggle.addEventListener("click", () => {
    const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    localStorage.setItem("secops-theme", next);
    syncToggle(next);
  });
}
