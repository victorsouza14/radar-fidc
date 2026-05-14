(function () {
  try {
    var t = localStorage.getItem("radar-theme");
    if (t === "light" || t === "dark") {
      document.documentElement.setAttribute("data-theme", t);
    }
  } catch (_) {}
})();
