(function () {
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("screen") || "inbox";
  const screens = Array.from(document.querySelectorAll(".screen"));
  const active = screens.some((screen) => screen.dataset.screen === requested) ? requested : "inbox";

  screens.forEach((screen) => {
    screen.classList.toggle("active", screen.dataset.screen === active);
  });

  document.querySelectorAll(".nav-list a").forEach((link) => {
    const target = new URL(link.href).searchParams.get("screen") || "inbox";
    link.classList.toggle("active", target === active);
    link.setAttribute("aria-current", target === active ? "page" : "false");
  });

  if (active === "login" || active === "unauthorized") {
    document.querySelector(".sidebar").style.display = "none";
    document.querySelector(".prototype-shell").style.gridTemplateColumns = "1fr";
  }
})();
