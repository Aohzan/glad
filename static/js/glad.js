/* Glad application shell: theme, sidebar, search, icons and form helpers.
 * Loaded on every page after Bootstrap. CSP forbids inline on* handlers, so
 * every behaviour is wired through delegated listeners and data-* attributes.
 */
(function () {
  'use strict';

  var root = document.documentElement;

  function store(key, value) {
    try {
      if (value === undefined) return localStorage.getItem(key);
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    } catch (e) { /* storage disabled */ }
    return null;
  }

  /* ── Design tokens ─────────────────────────────────────────────────── */

  function gToken(name) {
    return getComputedStyle(root).getPropertyValue('--g-' + name).trim();
  }

  function gChartColors() {
    return ['c1', 'c2', 'c3', 'c4', 'c5', 'c6'].map(gToken);
  }

  /* ── Icons ─────────────────────────────────────────────────────────── */

  var spriteMeta = document.querySelector('meta[name="glad-icon-sprite"]');
  var SPRITE = spriteMeta ? spriteMeta.content : '';

  // Same markup as the {% icon %} template tag, for HTML built in JS.
  function gIcon(name, cls) {
    var safe = String(name || '').replace(/[^a-z0-9-]/g, '');
    var extra = cls ? ' ' + String(cls).replace(/[^\w -]/g, '') : '';
    return '<svg class="g-icon' + extra + '" aria-hidden="true" focusable="false">' +
      '<use href="' + SPRITE + '#' + safe + '"></use></svg>';
  }

  /* ── ApexCharts defaults ───────────────────────────────────────────── */

  function applyApexGlobalDefaults(themeName) {
    var isDark = themeName === 'dark';
    var muted = gToken('muted');
    var line = gToken('line');
    window.APEX_HERO_COLORS = gChartColors();
    window.Apex = {
      colors: window.APEX_HERO_COLORS,
      chart: {
        background: 'transparent',
        foreColor: muted,
        fontFamily: 'inherit',
        animations: { easing: 'easeOutSine', dynamicAnimation: { easing: 'easeOutSine' } },
      },
      theme: { mode: isDark ? 'dark' : 'light' },
      tooltip: { theme: isDark ? 'dark' : 'light' },
      grid: { borderColor: line, strokeDashArray: 0 },
      xaxis: {
        axisBorder: { color: line },
        axisTicks: { color: line },
        labels: { style: { colors: gToken('dim') } },
      },
      yaxis: { labels: { style: { colors: gToken('dim') } } },
      legend: { labels: { colors: muted } },
      dataLabels: { style: { fontFamily: 'inherit' } },
    };
  }

  /* ── Theme ─────────────────────────────────────────────────────────── */

  function setTheme(themeName, savePreference) {
    root.setAttribute('data-bs-theme', themeName);
    applyApexGlobalDefaults(themeName);
    if (savePreference) store('theme', themeName);
    if (typeof window.updateChartsTheme === 'function') {
      window.updateChartsTheme(themeName);
    }
  }

  function toggleTheme() {
    setTheme(root.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark', true);
  }

  applyApexGlobalDefaults(root.getAttribute('data-bs-theme') || 'light');

  var colorScheme = window.matchMedia('(prefers-color-scheme: dark)');
  colorScheme.addEventListener('change', function (event) {
    if (!store('theme')) setTheme(event.matches ? 'dark' : 'light', false);
  });

  /* ── Sidebar and drawer ────────────────────────────────────────────── */

  function toggleSidebar() {
    var next = root.getAttribute('data-sidebar') === 'collapsed' ? 'expanded' : 'collapsed';
    root.setAttribute('data-sidebar', next);
    store('glad.sidebar', next);
  }

  function setDrawer(open) {
    root.classList.toggle('g-drawer-open', open);
    var opener = document.getElementById('g-drawer-open');
    if (opener) opener.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  // Group headers fold their items; only the current page's group starts open.
  function toggleNavGroup(head) {
    var open = head.getAttribute('aria-expanded') !== 'true';
    head.setAttribute('aria-expanded', open ? 'true' : 'false');
    var items = document.getElementById(head.getAttribute('aria-controls'));
    if (items) items.toggleAttribute('data-folded', !open);
  }

  // Sidebar entries show their name at once on hover: always when the
  // sidebar is reduced to icons, otherwise only when the name is truncated.
  var navTip = null;
  var TIP_TARGETS = '.g-nav__item, .g-sidebar__btn, .g-sidebar__toggle';

  function navTipText(el) {
    var text = el.querySelector('.g-nav__text, .g-sidebar__label');
    if (root.getAttribute('data-sidebar') === 'collapsed' && window.innerWidth >= 720) {
      return el.getAttribute('aria-label') || (text ? text.textContent : '');
    }
    return text && text.scrollWidth > text.clientWidth ? text.textContent : '';
  }

  function showNavTip(el) {
    var text = navTipText(el).trim();
    if (!text) return hideNavTip();
    if (!navTip) {
      navTip = document.createElement('div');
      navTip.className = 'g-nav-tip';
      navTip.setAttribute('role', 'tooltip');
      document.body.appendChild(navTip);
    }
    var rect = el.getBoundingClientRect();
    navTip.textContent = text;
    navTip.style.left = Math.round(rect.right + 8) + 'px';
    navTip.style.top = Math.round(rect.top + rect.height / 2) + 'px';
    navTip.hidden = false;
  }

  function hideNavTip() {
    if (navTip) navTip.hidden = true;
  }

  var sidebar = document.getElementById('g-sidebar');
  if (sidebar) {
    ['mouseover', 'focusin'].forEach(function (type) {
      sidebar.addEventListener(type, function (event) {
        var el = event.target.closest(TIP_TARGETS);
        if (el) showNavTip(el); else hideNavTip();
      });
    });
    ['mouseleave', 'focusout', 'click'].forEach(function (type) {
      sidebar.addEventListener(type, hideNavTip);
    });
    var nav = sidebar.querySelector('.g-nav');
    if (nav) nav.addEventListener('scroll', hideNavTip, { passive: true });
  }

  /* ── Header search (⌘K) ────────────────────────────────────────────── */

  var search = {
    box: document.getElementById('g-search'),
    input: document.getElementById('g-search-input'),
    results: document.getElementById('g-search-results'),
    items: null,
    matches: [],
    active: -1,
  };

  function normalize(text) {
    return String(text || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  }

  function loadSearchIndex() {
    if (search.items) return Promise.resolve(search.items);
    var cached = null;
    try { cached = JSON.parse(sessionStorage.getItem('glad.search') || 'null'); } catch (e) { cached = null; }
    if (cached) {
      search.items = cached;
      return Promise.resolve(cached);
    }
    return fetch(search.box.dataset.url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.ok ? r.json() : { items: [] }; })
      .then(function (data) {
        search.items = data.items || [];
        try { sessionStorage.setItem('glad.search', JSON.stringify(search.items)); } catch (e) { /* full */ }
        return search.items;
      })
      .catch(function () { search.items = []; return search.items; });
  }

  function closeSearch() {
    if (!search.results) return;
    search.results.hidden = true;
    search.input.setAttribute('aria-expanded', 'false');
    search.active = -1;
  }

  function highlight(index) {
    var nodes = search.results.querySelectorAll('.g-search__item');
    nodes.forEach(function (node, i) {
      node.classList.toggle('is-active', i === index);
      node.setAttribute('aria-selected', i === index ? 'true' : 'false');
    });
    search.active = index;
    if (nodes[index]) nodes[index].scrollIntoView({ block: 'nearest' });
  }

  function renderSearch() {
    var query = normalize(search.input.value.trim());
    var list = search.results;
    list.replaceChildren();
    if (!query) { closeSearch(); return; }
    search.matches = (search.items || []).filter(function (item) {
      return normalize(item.label + ' ' + item.sub).indexOf(query) !== -1;
    }).slice(0, 12);
    if (!search.matches.length) {
      var empty = document.createElement('div');
      empty.className = 'g-search__empty';
      empty.textContent = list.dataset.empty;
      list.appendChild(empty);
    }
    search.matches.forEach(function (item, i) {
      var link = document.createElement('a');
      link.className = 'g-search__item';
      link.href = item.url;
      link.setAttribute('role', 'option');
      link.dataset.index = i;
      link.insertAdjacentHTML('afterbegin', gIcon(item.icon));
      var text = document.createElement('span');
      text.className = 'g-search__text';
      var label = document.createElement('span');
      label.className = 'g-search__label';
      label.textContent = item.label;
      text.appendChild(label);
      if (item.sub) {
        var sub = document.createElement('span');
        sub.className = 'g-search__sub';
        sub.textContent = item.sub;
        text.appendChild(sub);
      }
      link.appendChild(text);
      list.appendChild(link);
    });
    list.hidden = false;
    search.input.setAttribute('aria-expanded', 'true');
    highlight(search.matches.length ? 0 : -1);
  }

  if (search.input) {
    search.input.addEventListener('focus', loadSearchIndex);
    search.input.addEventListener('input', function () {
      loadSearchIndex().then(renderSearch);
    });
    search.input.addEventListener('keydown', function (event) {
      var count = search.matches.length;
      if (event.key === 'ArrowDown' && count) {
        event.preventDefault();
        highlight((search.active + 1) % count);
      } else if (event.key === 'ArrowUp' && count) {
        event.preventDefault();
        highlight((search.active - 1 + count) % count);
      } else if (event.key === 'Enter' && search.active >= 0 && !search.results.hidden) {
        event.preventDefault();
        window.location.href = search.matches[search.active].url;
      } else if (event.key === 'Escape') {
        search.input.value = '';
        closeSearch();
        search.input.blur();
      }
    });
  }

  /* ── Delegated listeners ───────────────────────────────────────────── */

  // A link or form inside a collapse toggle (a clickable table row) keeps its
  // own action instead of toggling the row: Bootstrap would cancel the link.
  // Bootstrap listens in the capture phase on the document, so the guard sits
  // on the window, which the capture phase reaches first.
  window.addEventListener('click', function (event) {
    if (event.target.closest('[data-bs-toggle="collapse"] a, [data-bs-toggle="collapse"] form')) {
      event.stopPropagation();
    }
  }, true);

  document.addEventListener('keydown', function (event) {
    var toggle = event.target.closest('[role="button"][data-bs-toggle]');
    if (toggle && toggle === event.target && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      toggle.click();
    }
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k' && search.input) {
      event.preventDefault();
      search.input.focus();
      search.input.select();
    }
    if (event.key === 'Escape') setDrawer(false);
  });

  document.addEventListener('click', function (event) {
    var target = event.target;
    if (target.closest('#theme-toggle')) toggleTheme();
    if (target.closest('#g-sidebar-toggle')) toggleSidebar();
    var navGroup = target.closest('[data-g-nav-group]');
    if (navGroup) toggleNavGroup(navGroup);
    if (target.closest('#g-drawer-open')) setDrawer(true);
    if (target.closest('[data-g-drawer-close]')) setDrawer(false);
    if (search.box && !target.closest('#g-search')) closeSearch();

    // <button data-confirm="..."> asks before acting; with data-submit-form="<id>"
    // it submits that form instead of its own.
    var button = target.closest('button[data-confirm]');
    if (button) {
      if (!window.confirm(button.dataset.confirm)) {
        event.preventDefault();
        event.stopImmediatePropagation();
        return;
      }
      if (button.dataset.submitForm) {
        event.preventDefault();
        var form = document.getElementById(button.dataset.submitForm);
        if (form) form.submit();
      }
    }
  });

  // <form data-confirm="..."> asks for confirmation before submitting; a
  // submission nobody cancelled shows the loading bar and locks its buttons.
  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (form.matches('form[data-confirm]') && !window.confirm(form.dataset.confirm)) {
      event.preventDefault();
    }
    if (event.defaultPrevented) return;
    var bar = document.getElementById('loading-bar');
    if (bar) bar.classList.add('visible');
    form.querySelectorAll('[type="submit"]').forEach(function (btn) { btn.disabled = true; });
  });

  // <select data-submit-on-change> submits its form on change.
  document.addEventListener('change', function (event) {
    if (event.target.matches('[data-submit-on-change]') && event.target.form) {
      event.target.form.submit();
    }
  });

  /* ── Forms: Bootstrap classes, validation state, loading bar ───────── */

  function linkError(control, message) {
    if (!message.id) message.id = 'error_' + Math.random().toString(36).slice(2, 11);
    control.classList.add('is-invalid');
    var described = control.getAttribute('aria-describedby');
    if (!described || described.split(' ').indexOf(message.id) === -1) {
      control.setAttribute('aria-describedby', described ? described + ' ' + message.id : message.id);
    }
  }

  function decorateForms() {
    var controlSelector = 'input[type="text"], input[type="email"], input[type="password"], input[type="number"], ' +
      'input[type="date"], input[type="datetime-local"], input[type="file"], input[type="url"], input[type="tel"], textarea, select';
    document.querySelectorAll(controlSelector).forEach(function (input) {
      if (input.classList.contains('form-control') || input.classList.contains('form-select') ||
          input.classList.contains('form-check-input')) return;
      input.classList.add(input.tagName.toLowerCase() === 'select' ? 'form-select' : 'form-control');
    });

    document.querySelectorAll('input[type="checkbox"], input[type="radio"]').forEach(function (input) {
      if (!input.classList.contains('form-check-input') && !input.classList.contains('btn-check')) {
        input.classList.add('form-check-input');
      }
    });

    var controls = '.form-control, .form-select, .form-check-input';
    document.querySelectorAll('.invalid-feedback').forEach(function (message) {
      var control = message.previousElementSibling;
      while (control && !control.matches(controls)) control = control.previousElementSibling;
      if (!control) {
        var parent = message.closest('.mb-3, .col-12, .form-group');
        control = parent ? parent.querySelector(controls) : null;
      }
      if (control) linkError(control, message);
    });
  }

  /* ── Async panels: <div data-g-panel="url"> is replaced by the fragment ─ */

  function loadPanels() {
    document.querySelectorAll('[data-g-panel]').forEach(function (panel) {
      fetch(panel.dataset.gPanel, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(function (r) {
          if (!r.ok) throw new Error(r.status);
          return r.text();
        })
        .then(function (html) {
          // Fragments are server-rendered templates of this site (auto-escaped).
          panel.innerHTML = html;
          panel.removeAttribute('aria-busy');
          panel.dispatchEvent(new CustomEvent('g:panel-loaded', { bubbles: true }));
        })
        .catch(function () {
          var message = document.createElement('div');
          message.className = 'g-card g-panel-error';
          message.textContent = panel.dataset.gPanelError || '';
          panel.replaceChildren(message);
        });
    });
  }

  function ready() {
    decorateForms();
    loadPanels();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ready);
  } else {
    ready();
  }

  window.gToken = gToken;
  window.gChartColors = gChartColors;
  window.gIcon = gIcon;
  window.setTheme = setTheme;
  window.applyApexGlobalDefaults = applyApexGlobalDefaults;
})();
