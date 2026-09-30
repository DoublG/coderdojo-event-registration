/* @ds-bundle: {"format":4,"namespace":"CoderDojo","components":[
  {"name":"Button"},{"name":"Badge"},{"name":"NavBar"},{"name":"Hero"},
  {"name":"SessionCard"},{"name":"MentorCard"},{"name":"RegistrationCTA"},
  {"name":"EventCard"},{"name":"TicketPanel"},{"name":"PathwayCard"},{"name":"Testimonial"},
  {"name":"Table"},{"name":"Calendar"},{"name":"AwardCard"},{"name":"Form"},{"name":"Login"},{"name":"Wizard"},{"name":"AngledBanner"},
  {"name":"SearchTable"},{"name":"DojoFinder"},{"name":"AttendanceList"},{"name":"MagicLink"},{"name":"Notification"},{"name":"AdminNav"},
  {"name":"SponsorGrid"},{"name":"FAQAccordion"},{"name":"Footer"}
]} */
// The page's texts come from Django's JavaScript catalog (jsi18n/, loaded
// before this file); without it, gettext() just returns the English text.
if (typeof window.gettext !== "function") {
  window.gettext = function (text) { return text; };
}

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
        resendBtn.textContent = gettext("Sending…");
        setTimeout(function () {
          resendBtn.disabled = false;
          resendBtn.textContent = original;
          if (statusEl) statusEl.textContent = gettext("Link resent.");
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

  // Wires one notification bell's chrome: toggling the dropdown, closing it
  // on an outside click or Escape (returning focus to the bell). That's all
  // this does now — the content itself (unread count, item list, "Mark all
  // as read"'s disabled state) is real server-rendered data
  // (dojos/templates/dojos/partials/_notification_bell.html), pushed live
  // over the WebSocket the panel connects (see _admin_base.html's
  // ws-connect) and updated in place by "Mark all as read"'s own htmx
  // request — both replace this element outright via an out-of-band swap
  // matching its id, so this function is called again afterwards
  // (the htmx:oobAfterSwap listener at the bottom of this file) to re-wire
  // the fresh DOM. Clicking an item is a plain
  // navigating link (marks it read server-side, then redirects), not
  // something this function handles.
  function wireNotifications(container) {
    if (container.hasAttribute("data-cd-notif-wired")) return;
    container.setAttribute("data-cd-notif-wired", "");
    var toggle = container.querySelector("[data-cd-notif-toggle]");
    var panel = container.querySelector("[data-cd-notif-panel]");
    if (!toggle || !panel) return;

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
        pinBtn.setAttribute("aria-label", pinned ? gettext("Unpin sidebar") : gettext("Pin sidebar open"));
        pinBtn.title = pinned ? gettext("Unpin sidebar") : gettext("Pin sidebar open");
      }
      toggle.disabled = pinned;
      toggle.title = pinned ? gettext("Unpin the sidebar to hide it") : "";
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

  // Wires the "what am I managing" dropdown in the management sidebar's
  // brand area (core/templates/core/partials/_manage_switcher.html: the
  // organisation, its events, your dojos) — only rendered at all when the
  // account can manage more than one of those. Same toggle-panel
  // shape as wireNotifications (button + panel, close on outside click or
  // Escape) rather than anything AdminNav-specific, since switching dojos
  // is a plain link list, not another collapsible sidebar state.
  function wireDojoSwitcher(container) {
    var toggle = container.querySelector("[data-cd-adminnav-switcher-toggle]");
    var panel = container.querySelector("[data-cd-adminnav-switcher-menu]");
    if (!toggle || !panel) return;

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

    toggle.addEventListener("click", function (e) {
      e.stopPropagation();
      if (panel.hidden) openPanel();
      else closePanel();
    });
  }

  // Wires every [data-cd-adminnav-switcher] found under root (defaults to
  // the whole document) — same self-or-ancestor pattern as initNotifications.
  function initDojoSwitcher(root) {
    var scope = root || document;
    if (scope.hasAttribute && scope.hasAttribute("data-cd-adminnav-switcher")) {
      wireDojoSwitcher(scope);
      return;
    }
    var switchers = scope.querySelectorAll("[data-cd-adminnav-switcher]");
    for (var i = 0; i < switchers.length; i++) {
      wireDojoSwitcher(switchers[i]);
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
      button.title = gettext("Your browser doesn't support location lookup.");
      return;
    }

    button.addEventListener("click", function () {
      buttonLabel.textContent = gettext("Locating…");
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
          alert(gettext("Couldn't get your location — check your browser's location permission for this site and try again."));
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

  // Passkeys for two-step login (accounts/two_step.py): asks the browser to
  // make a passkey (mode "create", the Sign-in security page) or use one
  // (mode "get", the login's second step) with the options the server put in
  // the page as a json_script, then posts the answer in the form's hidden
  // field. Hand-written: WebAuthn is a browser API htmx can't reach.
  // Usage: CoderDojo.initPasskey(formEl, "options-script-id", "create" | "get")
  function base64urlToBuffer(value) {
    var base64 = value.replace(/-/g, "+").replace(/_/g, "/");
    var binary = atob(base64 + "===".slice((base64.length + 3) % 4));
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes.buffer;
  }

  function bufferToBase64url(buffer) {
    if (!buffer) return null;
    var bytes = new Uint8Array(buffer);
    var binary = "";
    for (var i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function initPasskey(form, optionsId, mode) {
    if (!form) return;
    var button = form.querySelector("[data-passkey-button]");
    var errorEl = form.querySelector("[data-passkey-error]");
    var field = form.querySelector(mode === "create" ? "[name=token]" : "[name$=otp_token]");
    var script = document.getElementById(optionsId);
    if (!button || !field || !script) return;

    function showError(text) {
      if (!errorEl) return;
      errorEl.textContent = text;
      errorEl.removeAttribute("hidden");
    }

    if (!window.PublicKeyCredential || !navigator.credentials) {
      button.disabled = true;
      showError(gettext("This browser can't use passkeys. Try another browser, or another way to confirm it's you."));
      return;
    }

    button.addEventListener("click", function () {
      var options = JSON.parse(script.textContent);
      if (typeof options === "string") options = JSON.parse(options);
      options.challenge = base64urlToBuffer(options.challenge);
      var listed = mode === "create" ? options.excludeCredentials : options.allowCredentials;
      (listed || []).forEach(function (credential) { credential.id = base64urlToBuffer(credential.id); });
      if (mode === "create") options.user.id = base64urlToBuffer(options.user.id);

      button.disabled = true;
      var call = mode === "create"
        ? navigator.credentials.create({ publicKey: options })
        : navigator.credentials.get({ publicKey: options });
      call.then(function (credential) {
        var response = credential.response;
        var answer = {
          id: credential.id,
          rawId: bufferToBase64url(credential.rawId),
          type: credential.type,
          response: { clientDataJSON: bufferToBase64url(response.clientDataJSON) },
        };
        if (mode === "create") {
          answer.response.attestationObject = bufferToBase64url(response.attestationObject);
          if (response.getTransports) answer.response.transports = response.getTransports();
        } else {
          answer.response.authenticatorData = bufferToBase64url(response.authenticatorData);
          answer.response.signature = bufferToBase64url(response.signature);
          answer.response.userHandle = bufferToBase64url(response.userHandle);
        }
        field.value = JSON.stringify(answer);
        form.submit();
      }, function () {
        button.disabled = false;
        showError(mode === "create"
          ? gettext("No passkey was made. You can try again.")
          : gettext("Your passkey wasn't used. Try again, or use another way to confirm it's you."));
      });
    });
  }

  // What inline handlers (onclick=, onsubmit=, hx-on) used to do: the
  // Content-Security-Policy blocks those (settings.CONTENT_SECURITY_POLICY),
  // so pages mark the element and these document-wide listeners act on it.
  //  - data-confirm="Question?" on a form, or on the submit button that
  //    needs it: asks before submitting, and cancels on "No".
  //  - data-autosubmit on a select: submits its form when it changes.
  //  - data-action="reload" | "print" | "close-details" on a button.
  document.addEventListener("submit", function (e) {
    var button = e.submitter;
    var message = (button && button.getAttribute("data-confirm")) || e.target.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
      e.preventDefault();
      e.stopImmediatePropagation();
    }
  }, true);

  document.addEventListener("change", function (e) {
    var field = e.target;
    if (field.hasAttribute && field.hasAttribute("data-autosubmit") && field.form) field.form.submit();
  });

  document.addEventListener("click", function (e) {
    var button = e.target.closest ? e.target.closest("[data-action]") : null;
    if (!button) return;
    var action = button.getAttribute("data-action");
    if (action === "reload") {
      window.location.reload();
    } else if (action === "print") {
      window.print();
    } else if (action === "close-details") {
      var details = button.closest("details");
      if (details) details.open = false;
    }
  });

  // The notification bell arrives as a fresh element on every out-of-band
  // swap (a WebSocket push, "Mark all as read"): wire the new one.
  document.addEventListener("htmx:oobAfterSwap", function (e) {
    if (e.target && e.target.classList && e.target.classList.contains("cd-notif")) initNotifications(e.target);
  });

  window.CoderDojo = {
    version: 1,
    initFaq: initFaq,
    initFaqItem: initFaqItem,
    initSearchTable: initSearchTable,
    initAttendance: initAttendance,
    initMagicLink: initMagicLink,
    initNotifications: initNotifications,
    initAdminNav: initAdminNav,
    initDojoSwitcher: initDojoSwitcher,
    initDojoLocationSearch: initDojoLocationSearch,
    initCarousel: initCarousel,
    initPasskey: initPasskey,
  };
})();