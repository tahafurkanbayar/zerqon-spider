/* Zerqon Spider — arayüz yardımcıları (vanilla JS, satır içi script yok — CSP uyumlu) */
(function () {
  "use strict";

  var THEMES = ["system", "light", "dark"];

  function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    var body = new URLSearchParams();
    body.set("theme", theme);
    fetch("/preferences/theme", { method: "POST", body: body, credentials: "same-origin" });
    var label = document.querySelector("[data-theme-label]");
    if (label) label.textContent = label.getAttribute("data-label-" + theme) || theme;
  }

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!(target instanceof Element)) return;

    var themeBtn = target.closest("[data-theme-toggle]");
    if (themeBtn) {
      var current = document.documentElement.getAttribute("data-theme") || "system";
      setTheme(THEMES[(THEMES.indexOf(current) + 1) % THEMES.length]);
      return;
    }

    var menuBtn = target.closest("[data-menu-toggle]");
    if (menuBtn) {
      var sidebar = document.querySelector(".sidebar");
      if (sidebar) sidebar.classList.toggle("open");
      return;
    }

    var selectAll = target.closest("[data-select-all]");
    if (selectAll && selectAll instanceof HTMLInputElement) {
      var scope = selectAll.closest("form") || document;
      scope.querySelectorAll("input[data-row-select]").forEach(function (box) {
        box.checked = selectAll.checked;
      });
      updateSelectionCount(scope);
      return;
    }

    if (target.matches("input[data-row-select]")) {
      updateSelectionCount(target.closest("form") || document);
    }
  });

  function updateSelectionCount(scope) {
    var count = scope.querySelectorAll("input[data-row-select]:checked").length;
    scope.querySelectorAll("[data-selection-count]").forEach(function (el) {
      el.textContent = String(count);
    });
    scope.querySelectorAll("[data-requires-selection]").forEach(function (el) {
      el.disabled = count === 0;
    });
  }

  // Onay isteyen normal formlar (HTMX dışı)
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (form instanceof HTMLFormElement && form.hasAttribute("data-confirm")) {
      if (!window.confirm(form.getAttribute("data-confirm"))) {
        event.preventDefault();
      }
    }
  });

  // Tarama başlatma: izin onayı işaretlenmeden düğme pasif
  document.addEventListener("change", function (event) {
    var target = event.target;
    if (target instanceof HTMLSelectElement && target.hasAttribute("data-autosubmit") && target.form) {
      target.form.submit();
      return;
    }
    if (target instanceof HTMLInputElement && target.hasAttribute("data-permission")) {
      var form = target.closest("form");
      if (form) {
        form.querySelectorAll("[data-requires-permission]").forEach(function (btn) {
          btn.disabled = !target.checked;
        });
      }
    }
  });

  // HTMX hata durumlarında kullanıcıya bilgi
  document.body.addEventListener("htmx:responseError", function (event) {
    var box = document.getElementById("global-error");
    if (box) {
      box.classList.remove("hidden");
    }
  });
})();
