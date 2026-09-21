/* @ds-bundle: {"format":4,"namespace":"CoderDojo","components":[
  {"name":"Button"},{"name":"Badge"},{"name":"NavBar"},{"name":"Hero"},
  {"name":"SessionCard"},{"name":"MentorCard"},{"name":"RegistrationCTA"},
  {"name":"EventCard"},{"name":"TicketPanel"},{"name":"PathwayCard"},{"name":"Testimonial"},
  {"name":"Table"},{"name":"Calendar"},{"name":"AwardCard"},{"name":"Form"},{"name":"Login"},{"name":"Wizard"},{"name":"AngledBanner"},
  {"name":"SearchTable"},{"name":"DojoFinder"},{"name":"AttendanceList"},{"name":"MagicLink"},{"name":"Notification"},{"name":"AdminNav"},
  {"name":"SponsorGrid"},{"name":"FAQAccordion"},{"name":"Footer"}
]} */
(function () {
  "use strict";

  // Wires a single FAQ item's toggle button to show/hide its answer.
  // Usage: CoderDojo.initFaqItem(buttonEl, answerEl)
  function initFaqItem(button, answer) {
    if (!button || !answer) return;
    button.setAttribute("aria-expanded", "false");
    button.addEventListener("click", function () {
      var isOpen = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", String(!isOpen));
      button.closest(".cd-faq__item").setAttribute("data-open", String(!isOpen));
      if (isOpen) {
        answer.setAttribute("hidden", "");
      } else {
        answer.removeAttribute("hidden");
      }
    });
  }

  // Wires every .cd-faq__item found under root (defaults to the whole document).
  function initFaq(root) {
    var scope = root || document;
    var items = scope.querySelectorAll(".cd-faq__item");
    for (var i = 0; i < items.length; i++) {
      var button = items[i].querySelector(".cd-faq__question");
      var answer = items[i].querySelector(".cd-faq__answer");
      initFaqItem(button, answer);
    }
  }

  // Wires one search-table's input to filter its rows as the visitor types.
  // A row matches on its data-cd-search-text (recommended: name + every
  // filterable field, lowercased) or, if that's absent, its own text content.
  function wireSearchTable(container) {
    var input = container.querySelector(".cd-search-table__input");
    if (!input) return;
    var rows = container.querySelectorAll("[data-cd-search-row]");
    var countEl = container.querySelector("[data-cd-search-count]");
    var emptyEl = container.querySelector("[data-cd-search-empty]");
    var emptyQueryEl = container.querySelector("[data-cd-search-empty-query]");

    function apply() {
      var q = input.value.trim().toLowerCase();
      var shown = 0;
      for (var i = 0; i < rows.length; i++) {
        var row = rows[i];
        var text = (row.getAttribute("data-cd-search-text") || row.textContent || "").toLowerCase();
        if (q === "" || text.indexOf(q) !== -1) {
          row.hidden = false;
          shown++;
        } else {
          row.hidden = true;
        }
      }
      if (countEl) countEl.textContent = shown + (shown === 1 ? " result" : " results");
      if (emptyEl) emptyEl.hidden = shown !== 0;
      if (emptyQueryEl) emptyQueryEl.textContent = input.value.trim();
    }

    input.addEventListener("input", apply);
    apply();
  }

  // Wires every .cd-search-table found under root (defaults to the whole document).
  // root may be a .cd-search-table itself, or any ancestor containing one or more.
  function initSearchTable(root) {
    var scope = root || document;
    if (scope.classList && scope.classList.contains("cd-search-table")) {
      wireSearchTable(scope);
      return;
    }
    var tables = scope.querySelectorAll(".cd-search-table");
    for (var i = 0; i < tables.length; i++) {
      wireSearchTable(tables[i]);
    }
  }

  // Sets one attendance row's toggle to "present", "absent", or (re-clicking
  // the already-pressed button) "none", updating both buttons' aria-pressed.
  function setAttendanceState(row, state) {
    var present = row.querySelector('[data-cd-attendance-btn="present"]');
    var absent = row.querySelector('[data-cd-attendance-btn="absent"]');
    if (present) present.setAttribute("aria-pressed", String(state === "present"));
    if (absent) absent.setAttribute("aria-pressed", String(state === "absent"));
  }

  // Wires one attendance list: per-row Present/Absent toggles, an optional
  // "Mark all present" button, and a live "N of M present" summary.
  function wireAttendance(container) {
    var rows = container.querySelectorAll("[data-cd-attendance-row]");
    if (!rows.length) return;
    var summaryEl = container.querySelector("[data-cd-attendance-summary]");
    var markAllBtn = container.querySelector("[data-cd-attendance-mark-all]");

    function updateSummary() {
      if (!summaryEl) return;
      var present = 0;
      for (var i = 0; i < rows.length; i++) {
        var btn = rows[i].querySelector('[data-cd-attendance-btn="present"]');
        if (btn && btn.getAttribute("aria-pressed") === "true") present++;
      }
      summaryEl.textContent = present + " of " + rows.length + " present";
    }

    for (var i = 0; i < rows.length; i++) {
      (function (row) {
        var buttons = row.querySelectorAll("[data-cd-attendance-btn]");
        for (var j = 0; j < buttons.length; j++) {
          buttons[j].addEventListener("click", function () {
            var state = this.getAttribute("data-cd-attendance-btn");
            var alreadyOn = this.getAttribute("aria-pressed") === "true";
            setAttendanceState(row, alreadyOn ? "none" : state);
            updateSummary();
          });
        }
      })(rows[i]);
    }

    if (markAllBtn) {
      markAllBtn.addEventListener("click", function () {
        for (var i = 0; i < rows.length; i++) setAttendanceState(rows[i], "present");
        updateSummary();
      });
    }

    updateSummary();
  }

  // Wires every .cd-attendance found under root (defaults to the whole document).
  // root may be a .cd-attendance itself, or any ancestor containing one or more.
  function initAttendance(root) {
    var scope = root || document;
    if (scope.classList && scope.classList.contains("cd-attendance")) {
      wireAttendance(scope);
      return;
    }
    var lists = scope.querySelectorAll(".cd-attendance");
    for (var i = 0; i < lists.length; i++) {
      wireAttendance(lists[i]);
    }
  }

  // Wires one magic-link login card: submitting the request form swaps to
  // the "check your email" panel (filling in the address that was sent to),
  // "Use a different email address" swaps back, and "Resend" briefly
  // disables itself before confirming a second link was sent.
  function wireMagicLink(container) {
    var form = container.querySelector("[data-cd-magic-link-form]");
    if (!form) return;
    var emailInput = form.querySelector('input[type="email"]');
    var requestPanel = container.querySelector("[data-cd-magic-link-request]");
    var sentPanel = container.querySelector("[data-cd-magic-link-sent]");
    var emailDisplay = container.querySelector("[data-cd-magic-link-email]");
    var resendBtn = container.querySelector("[data-cd-magic-link-resend]");
    var changeLink = container.querySelector("[data-cd-magic-link-change]");
    var statusEl = container.querySelector("[data-cd-magic-link-status]");

    function showSent(email) {
      if (emailDisplay) emailDisplay.textContent = email;
      if (statusEl) statusEl.textContent = "";
      if (requestPanel) requestPanel.hidden = true;
      if (sentPanel) sentPanel.hidden = false;
      if (resendBtn) resendBtn.focus();
    }

    function showRequest() {
      if (sentPanel) sentPanel.hidden = true;
      if (requestPanel) requestPanel.hidden = false;
      if (statusEl) statusEl.textContent = "";
      if (emailInput) emailInput.focus();
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (typeof form.reportValidity === "function" && !form.reportValidity()) return;
      showSent(emailInput ? emailInput.value.trim() : "");
    });

    if (changeLink) {
      changeLink.addEventListener("click", function (e) {
        e.preventDefault();
        showRequest();
      });
    }

    if (resendBtn) {
      resendBtn.addEventListener("click", function () {
        var original = resendBtn.textContent;
        resendBtn.disabled = true;
        resendBtn.textContent = "Sending…";
        setTimeout(function () {
          resendBtn.disabled = false;
          resendBtn.textContent = original;
          if (statusEl) statusEl.textContent = "Link resent.";
        }, 900);
      });
    }
  }

  // Wires every .cd-magic-link found under root (defaults to the whole document).
  // root may be a .cd-magic-link itself, or any ancestor containing one or more.
  function initMagicLink(root) {
    var scope = root || document;
    if (scope.classList && scope.classList.contains("cd-magic-link")) {
      wireMagicLink(scope);
      return;
    }
    var cards = scope.querySelectorAll(".cd-magic-link");
    for (var i = 0; i < cards.length; i++) {
      wireMagicLink(cards[i]);
    }
  }

  // Wires one notification bell: toggling the dropdown, closing it on an
  // outside click or Escape (returning focus to the bell), marking a single
  // item read on click, "Mark all as read," and the unread count badge.
  function wireNotifications(container) {
    var toggle = container.querySelector("[data-cd-notif-toggle]");
    var panel = container.querySelector("[data-cd-notif-panel]");
    if (!toggle || !panel) return;
    var countEl = container.querySelector("[data-cd-notif-count]");
    var markAllBtn = container.querySelector("[data-cd-notif-mark-all]");
    var items = container.querySelectorAll("[data-cd-notif-item]");

    function updateCount() {
      var unread = 0;
      for (var i = 0; i < items.length; i++) {
        if (items[i].hasAttribute("data-unread")) unread++;
      }
      if (countEl) {
        countEl.textContent = String(unread);
        countEl.hidden = unread === 0;
      }
      if (markAllBtn) markAllBtn.disabled = unread === 0;
    }

    function onDocClick(e) {
      if (!container.contains(e.target)) closePanel();
    }
    function onKeydown(e) {
      if (e.key === "Escape") closePanel(true);
    }

    function openPanel() {
      panel.hidden = false;
      toggle.setAttribute("aria-expanded", "true");
      document.addEventListener("click", onDocClick);
      document.addEventListener("keydown", onKeydown);
    }
    function closePanel(focusToggle) {
      panel.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
      document.removeEventListener("click", onDocClick);
      document.removeEventListener("keydown", onKeydown);
      if (focusToggle) toggle.focus();
    }

    toggle.setAttribute("aria-expanded", "false");
    toggle.addEventListener("click", function (e) {
      e.stopPropagation();
      if (panel.hidden) openPanel();
      else closePanel();
    });

    for (var i = 0; i < items.length; i++) {
      (function (item) {
        var btn = item.querySelector("[data-cd-notif-item-btn]");
        if (!btn) return;
        btn.addEventListener("click", function () {
          item.removeAttribute("data-unread");
          updateCount();
        });
      })(items[i]);
    }

    if (markAllBtn) {
      markAllBtn.addEventListener("click", function () {
        for (var i = 0; i < items.length; i++) items[i].removeAttribute("data-unread");
        updateCount();
      });
    }

    updateCount();
  }

  // Wires every .cd-notif found under root (defaults to the whole document).
  // root may be a .cd-notif itself, or any ancestor containing one or more.
  function initNotifications(root) {
    var scope = root || document;
    if (scope.classList && scope.classList.contains("cd-notif")) {
      wireNotifications(scope);
      return;
    }
    var groups = scope.querySelectorAll(".cd-notif");
    for (var i = 0; i < groups.length; i++) {
      wireNotifications(groups[i]);
    }
  }

  // Wires one admin sidebar: the mobile "Menu" toggle opens it as an
  // off-canvas panel with a backdrop (only visible below the 900px
  // breakpoint — at desktop widths this all sits inertly hidden), Escape
  // and a backdrop click close it and return focus to the toggle, and
  // clicking any nav link closes it too (a real navigation would leave the
  // page anyway; this just keeps a stale open drawer from lingering when
  // markup is reused as a single-page demo).
  function wireAdminNav(shell) {
    var toggle = shell.querySelector("[data-cd-adminnav-toggle]");
    var nav = shell.querySelector("[data-cd-adminnav]");
    var backdrop = shell.querySelector("[data-cd-adminnav-backdrop]");
    if (!toggle || !nav) return;

    function onKeydown(e) {
      if (e.key === "Escape") closeNav(true);
    }

    function openNav() {
      nav.setAttribute("data-open", "true");
      if (backdrop) backdrop.setAttribute("data-open", "true");
      toggle.setAttribute("aria-expanded", "true");
      document.addEventListener("keydown", onKeydown);
    }
    function closeNav(focusToggle) {
      nav.setAttribute("data-open", "false");
      if (backdrop) backdrop.setAttribute("data-open", "false");
      toggle.setAttribute("aria-expanded", "false");
      document.removeEventListener("keydown", onKeydown);
      if (focusToggle) toggle.focus();
    }

    toggle.addEventListener("click", function () {
      if (nav.getAttribute("data-open") === "true") closeNav();
      else openNav();
    });
    if (backdrop) backdrop.addEventListener("click", function () { closeNav(); });

    var links = nav.querySelectorAll(".cd-admin-nav__link");
    for (var i = 0; i < links.length; i++) {
      links[i].addEventListener("click", function () { closeNav(); });
    }
  }

  // Wires every .cd-admin-nav-shell found under root (defaults to the whole
  // document). root may be a .cd-admin-nav-shell itself, or any ancestor
  // containing one or more.
  function initAdminNav(root) {
    var scope = root || document;
    if (scope.classList && scope.classList.contains("cd-admin-nav-shell")) {
      wireAdminNav(scope);
      return;
    }
    var shells = scope.querySelectorAll(".cd-admin-nav-shell");
    for (var i = 0; i < shells.length; i++) {
      wireAdminNav(shells[i]);
    }
  }

  window.CoderDojo = {
    version: 1,
    initFaq: initFaq,
    initFaqItem: initFaqItem,
    initSearchTable: initSearchTable,
    initAttendance: initAttendance,
    initMagicLink: initMagicLink,
    initNotifications: initNotifications,
    initAdminNav: initAdminNav
  };
})();