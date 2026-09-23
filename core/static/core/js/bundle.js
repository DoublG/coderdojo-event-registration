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

  // Wires one admin sidebar. The same "Menu" toggle does two different
  // things depending on viewport, since below 900px there's no spare width
  // for a permanent sidebar and above it there is:
  //  - Below 900px: opens/closes the nav as an off-canvas drawer with a
  //    backdrop, Escape and a backdrop click close it and return focus to
  //    the toggle, and clicking any nav link closes it too (a real
  //    navigation would leave the page anyway; this just keeps a stale
  //    open drawer from lingering when markup is reused as a single-page
  //    demo).
  //  - At 901px and up: collapses the sidebar to zero width in place (no
  //    backdrop, nothing overlays the content) so the page content next to
  //    it can expand to use the full width. `inert` is set on the nav
  //    while collapsed so its links can't be tabbed to or found by a
  //    screen reader while invisible, and cleared the moment the sidebar
  //    is expanded again or the viewport drops back below 900px.
  //
  // A `.cd-admin-nav__pin` button (901px+ only, lives inside the nav
  // itself) locks the sidebar open: while pinned, the Menu toggle is
  // disabled so it can't be collapsed by mistake. Both the pinned flag and
  // the collapsed/expanded choice are remembered in localStorage per
  // shell (keyed by the shell's own id, so this design system's own
  // catalog — which can show more than one AdminNav demo on one page at
  // once — doesn't have one demo's toggle silently affect another's), and
  // restored the next time this page loads. localStorage reads/writes are
  // wrapped in try/catch since it can throw in a private window or with
  // site data blocked; the sidebar still works, it just won't remember.
  function wireAdminNav(shell) {
    var toggle = shell.querySelector("[data-cd-adminnav-toggle]");
    var nav = shell.querySelector("[data-cd-adminnav]");
    var backdrop = shell.querySelector("[data-cd-adminnav-backdrop]");
    var pinBtn = shell.querySelector("[data-cd-adminnav-pin]");
    if (!toggle || !nav) return;
    var desktopQuery = window.matchMedia("(min-width: 901px)");
    var storagePrefix = "cd-adminnav:" + (shell.id || "default") + ":";

    function readStored(key, fallback) {
      try {
        var v = window.localStorage.getItem(storagePrefix + key);
        return v === null ? fallback : v === "true";
      } catch (e) {
        return fallback;
      }
    }
    function writeStored(key, value) {
      try {
        window.localStorage.setItem(storagePrefix + key, String(value));
      } catch (e) {
        // ignore — private window, blocked storage, etc.
      }
    }

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

    function syncInert() {
      var collapsed = shell.getAttribute("data-collapsed") === "true";
      if (collapsed && desktopQuery.matches) nav.setAttribute("inert", "");
      else nav.removeAttribute("inert");
    }
    function setCollapsed(collapsed, persist) {
      shell.setAttribute("data-collapsed", collapsed ? "true" : "false");
      toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
      syncInert();
      if (persist !== false) writeStored("collapsed", collapsed);
    }
    function setPinned(pinned, persist) {
      shell.setAttribute("data-pinned", pinned ? "true" : "false");
      if (pinBtn) {
        pinBtn.setAttribute("aria-pressed", pinned ? "true" : "false");
        pinBtn.setAttribute("aria-label", pinned ? "Unpin sidebar" : "Pin sidebar open");
        pinBtn.title = pinned ? "Unpin sidebar" : "Pin sidebar open";
      }
      toggle.disabled = pinned;
      toggle.title = pinned ? "Unpin the sidebar to hide it" : "";
      if (pinned) setCollapsed(false, persist); // pinning always shows it, and locks it there
      if (persist !== false) writeStored("pinned", pinned);
    }
    if (desktopQuery.addEventListener) desktopQuery.addEventListener("change", syncInert);
    else if (desktopQuery.addListener) desktopQuery.addListener(syncInert); // older Safari

    toggle.addEventListener("click", function () {
      if (desktopQuery.matches) {
        if (shell.getAttribute("data-pinned") === "true") return; // locked open
        setCollapsed(shell.getAttribute("data-collapsed") !== "true");
      } else if (nav.getAttribute("data-open") === "true") {
        closeNav();
      } else {
        openNav();
      }
    });
    if (backdrop) backdrop.addEventListener("click", function () { closeNav(); });
    if (pinBtn) {
      pinBtn.addEventListener("click", function () {
        setPinned(shell.getAttribute("data-pinned") !== "true");
      });
    }

    var links = nav.querySelectorAll(".cd-admin-nav__link");
    for (var i = 0; i < links.length; i++) {
      links[i].addEventListener("click", function () { closeNav(); });
    }

    // Restore last session's choice. setPinned(..., false) / setCollapsed(...,
    // false) apply the state without re-writing what was just read back.
    setPinned(readStored("pinned", false), false);
    if (shell.getAttribute("data-pinned") !== "true") {
      setCollapsed(readStored("collapsed", false), false);
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

  // Wires a dojo-search form's "Use my location" button to the browser
  // Geolocation API, filling the form's hidden lat/lon fields and
  // (re-)submitting. Shared between the full dojo-finder page and the
  // homepage's embedded widget — both forms follow the same field/id
  // contract: a [name=location] text input, hidden [name=lat]/[name=lon]
  // fields, and a button with [data-cd-use-my-location] containing a
  // <span> label.
  //
  // Uses requestSubmit() rather than submit(): submit() does not fire a
  // "submit" event, so on an htmx-enhanced form it would silently bypass
  // htmx's hx-get entirely and just do nothing.
  function initDojoLocationSearch(form) {
    if (!form) return;
    var button = form.querySelector("[data-cd-use-my-location]");
    var buttonLabel = button && button.querySelector("span");
    var latField = form.querySelector("[name=lat]");
    var lonField = form.querySelector("[name=lon]");
    var locationField = form.querySelector("[name=location]");
    if (!button || !buttonLabel || !latField || !lonField || !locationField) return;
    var defaultLabel = buttonLabel.textContent;

    // Typing a new address means "search for this", not "still use my
    // location" — without this, a stale lat/lon from an earlier "Use my
    // location" search (re-rendered into these hidden fields by the bound
    // form on every reload) would silently keep overriding the address
    // the user just typed, since the view prefers lat/lon when present.
    locationField.addEventListener("input", function () {
      latField.value = "";
      lonField.value = "";
    });

    if (!navigator.geolocation) {
      button.disabled = true;
      button.title = "Your browser doesn't support location lookup.";
      return;
    }

    button.addEventListener("click", function () {
      buttonLabel.textContent = "Locating…";
      button.disabled = true;

      navigator.geolocation.getCurrentPosition(
        function (position) {
          // Left blank on purpose: the view treats a filled-in location
          // field as "the user typed an address, use that" and would
          // otherwise ignore these coordinates in favor of geocoding
          // whatever text sits here.
          locationField.value = "";
          latField.value = position.coords.latitude;
          lonField.value = position.coords.longitude;
          buttonLabel.textContent = defaultLabel;
          button.disabled = false;
          form.requestSubmit();
        },
        function () {
          buttonLabel.textContent = defaultLabel;
          button.disabled = false;
          alert("Couldn't get your location — check your browser's location permission for this site and try again.");
        },
        { timeout: 10000 }
      );
    });
  }

  // Shared prev/next scroll-snap carousel behaviour (pathways, upcoming
  // sessions, ...). `cardSelector` finds one card to measure its width +
  // gap for a "one page" scroll step. Content can be static or grow via
  // htmx (e.g. lazy-loaded carousel batches) — either way scrollWidth is
  // re-measured on every scroll/resize/htmx swap.
  function initCarousel(track, prevBtn, nextBtn, cardSelector) {
    if (!track || !prevBtn || !nextBtn) return;

    function stepSize() {
      var card = track.querySelector(cardSelector);
      if (!card) return track.clientWidth;
      var gap = parseFloat(getComputedStyle(track).columnGap || getComputedStyle(track).gap || "0");
      return card.getBoundingClientRect().width + gap;
    }

    function updateButtons() {
      var maxScroll = track.scrollWidth - track.clientWidth - 1;
      prevBtn.disabled = track.scrollLeft <= 0;
      nextBtn.disabled = track.scrollLeft >= maxScroll;
    }

    prevBtn.addEventListener("click", function () {
      track.scrollBy({ left: -stepSize(), behavior: "smooth" });
    });
    nextBtn.addEventListener("click", function () {
      track.scrollBy({ left: stepSize(), behavior: "smooth" });
    });
    track.addEventListener("scroll", updateButtons);
    track.addEventListener("htmx:afterSwap", updateButtons);
    window.addEventListener("resize", updateButtons);
    updateButtons();
  }

  window.CoderDojo = {
    version: 1,
    initFaq: initFaq,
    initFaqItem: initFaqItem,
    initSearchTable: initSearchTable,
    initAttendance: initAttendance,
    initMagicLink: initMagicLink,
    initNotifications: initNotifications,
    initAdminNav: initAdminNav,
    initDojoLocationSearch: initDojoLocationSearch,
    initCarousel: initCarousel,
  };
})();