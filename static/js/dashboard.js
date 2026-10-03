/* Dashboard: net worth chart and asset registry filters.
 * The figures arrive as server-rendered panels (see glad.js loadPanels); this
 * script wires them once the overview panel is in the page.
 */
(function () {
  'use strict';

  var script = document.getElementById('dashboard-script');
  var i18nNode = document.getElementById('dashboard-i18n');
  var i18n = i18nNode ? JSON.parse(i18nNode.textContent) : {};
  var lang = document.documentElement.lang || 'en';
  var MINUS = '−';

  function money(value, currency) {
    return new Intl.NumberFormat(lang, {
      style: 'currency', currency: currency, maximumFractionDigits: 0, minimumFractionDigits: 0,
    }).format(value).replace('-', MINUS);
  }

  function compact(value, currency) {
    return new Intl.NumberFormat(lang, {
      style: 'currency', currency: currency, notation: 'compact', maximumFractionDigits: 2,
    }).format(value).replace('-', MINUS);
  }

  function percent(value, signed, digits) {
    if (value === null || !isFinite(value)) return '—';
    return new Intl.NumberFormat(lang, {
      style: 'percent',
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
      signDisplay: signed ? 'exceptZero' : 'auto',
    }).format(value / 100).replace('-', MINUS);
  }

  function change(value, old) {
    return old ? (value - old) / Math.abs(old) * 100 : null;
  }

  function setTone(node, value) {
    node.classList.toggle('g-pos', value > 0);
    node.classList.toggle('g-neg', value < 0);
  }

  function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  /* ── Net worth chart ───────────────────────────────────────────────── */

  var chart = null;
  var cache = {};
  var state = { range: 1, gross: true, data: null, currency: 'EUR' };

  function monthLabel(iso, long) {
    var date = new Date(iso + 'T00:00:00');
    return new Intl.DateTimeFormat(lang, long ? { month: 'long', year: 'numeric' } : { month: 'short', year: '2-digit' }).format(date);
  }

  function chartOptions(data) {
    var accent = gToken('accent');
    var dim = gToken('dim');
    var series = [{ name: i18n.net, type: 'area', data: data.net }];
    if (state.gross) series.push({ name: i18n.gross, type: 'line', data: data.gross });
    return {
      chart: { height: 280, type: 'line', toolbar: { show: false }, zoom: { enabled: false }, fontFamily: 'inherit', parentHeightOffset: 0 },
      series: series,
      colors: [accent, dim],
      stroke: { curve: 'straight', width: [2.25, 1.5], dashArray: [0, 5] },
      fill: {
        type: ['gradient', 'solid'],
        opacity: [1, 1],
        gradient: { shadeIntensity: 0, opacityFrom: 0.22, opacityTo: 0, stops: [0, 100] },
      },
      dataLabels: { enabled: false },
      legend: { show: false },
      markers: { size: 0, hover: { size: 5 } },
      grid: { borderColor: gToken('line'), strokeDashArray: 0, xaxis: { lines: { show: false } }, padding: { left: 8, right: 8 } },
      labels: data.dates,
      xaxis: {
        type: 'category',
        tickAmount: 4,
        axisBorder: { show: false },
        axisTicks: { show: false },
        labels: { rotate: 0, hideOverlappingLabels: true, style: { colors: dim }, formatter: function (v) { return v ? monthLabel(v) : ''; } },
        tooltip: { enabled: false },
        crosshairs: { stroke: { color: gToken('line-strong'), width: 1, dashArray: 0 } },
      },
      yaxis: {
        tickAmount: 3,
        labels: { style: { colors: dim }, formatter: function (v) { return compact(v, state.currency); } },
      },
      tooltip: {
        shared: true,
        custom: function (ctx) {
          var i = ctx.dataPointIndex;
          var rows = [[i18n.net, data.net[i], true], [i18n.gross, data.gross[i], false], [i18n.debt, data.debt[i], false]];
          return '<div class="g-chart-tip"><span class="g-chart-tip__title">' + escapeHtml(monthLabel(data.dates[i], true)) + '</span>' +
            rows.map(function (r) {
              return '<span class="g-muted">' + escapeHtml(r[0]) + '</span><span class="' + (r[2] ? 'g-strong' : '') + '">' + escapeHtml(money(r[1], state.currency)) + '</span>';
            }).join('') + '</div>';
        },
      },
    };
  }

  function drawChart() {
    var node = document.getElementById('chart-evolution');
    if (!node || !state.data || typeof ApexCharts === 'undefined') return;
    if (chart) chart.destroy();
    chart = new ApexCharts(node, chartOptions(state.data));
    chart.render();
  }

  function loadChart(range) {
    state.range = range;
    var url = script.dataset.chartUrl + '?range=' + encodeURIComponent(range);
    var request = cache[range] || (cache[range] = fetch(url).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }));
    request.then(function (data) {
      if (state.range !== range) return;
      state.data = data;
      state.currency = data.currency || state.currency;
      drawChart();
    }).catch(function () {
      delete cache[range];
      var node = document.getElementById('chart-evolution');
      if (node) {
        var message = document.createElement('p');
        message.className = 'g-muted text-center py-5 mb-0';
        message.textContent = i18n.error || '';
        node.replaceChildren(message);
      }
    });
  }

  window.updateChartsTheme = drawChart;

  /* ── Registry filters ──────────────────────────────────────────────── */

  var filters = { kind: '', holder: '' };

  function plural(node, count) {
    return count + ' ' + (count > 1 ? node.dataset.many : node.dataset.one);
  }

  function applyFilters() {
    var registry = document.getElementById('registry');
    if (!registry) return;
    var currency = registry.dataset.currency;
    var net = parseFloat(registry.dataset.total) || 0;
    var totals = { value: 0, old: 0, count: 0 };

    registry.querySelectorAll('[data-g-group]').forEach(function (group) {
      var kind = group.dataset.gGroup;
      var sum = { value: 0, old: 0, count: 0 };
      registry.querySelectorAll('.g-table__row[data-kind="' + kind + '"]').forEach(function (row) {
        var visible = (!filters.kind || filters.kind === kind) && (!filters.holder || row.dataset.holder === filters.holder);
        row.hidden = !visible;
        if (!visible) return;
        sum.value += parseFloat(row.dataset.value) || 0;
        sum.old += parseFloat(row.dataset.old) || 0;
        sum.count += 1;
      });
      group.hidden = sum.count === 0;
      group.querySelector('[data-g-count]').textContent = plural(group.querySelector('[data-g-count]'), sum.count);
      group.querySelector('[data-g-value]').textContent = money(sum.value, currency);
      var groupChange = change(sum.value, sum.old);
      var changeNode = group.querySelector('[data-g-change]');
      changeNode.textContent = percent(groupChange, true, 2);
      setTone(changeNode, groupChange);
      group.querySelector('[data-g-weight]').textContent = percent(net ? sum.value / net * 100 : null, false, 1);
      totals.value += sum.value;
      totals.old += sum.old;
      totals.count += sum.count;
    });

    var activeGroup = filters.kind && registry.querySelector('[data-g-group="' + filters.kind + '"]');
    var title = document.getElementById('registry-title');
    title.textContent = activeGroup ? activeGroup.dataset.label : title.dataset.default;
    var count = document.getElementById('registry-count');
    count.textContent = plural(count, totals.count);
    document.getElementById('registry-total').textContent = money(totals.value, currency);
    var totalChange = change(totals.value, totals.old);
    var totalChangeNode = document.getElementById('registry-change');
    totalChangeNode.textContent = percent(totalChange, true, 2);
    setTone(totalChangeNode, totalChange);
    document.getElementById('registry-weight').textContent = percent(net ? totals.value / net * 100 : null, false, 1);
    document.getElementById('registry-empty').hidden = totals.count > 0;
    document.getElementById('registry-reset').hidden = !filters.kind && !filters.holder;

    document.querySelectorAll('[data-g-filter-class]').forEach(function (cell) {
      cell.setAttribute('aria-pressed', cell.dataset.gFilterClass === filters.kind ? 'true' : 'false');
    });
    document.querySelectorAll('[data-g-filter-holder]').forEach(function (button) {
      var on = button.dataset.gFilterHolder === filters.holder;
      button.classList.toggle('is-active', on);
      button.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }

  document.addEventListener('click', function (event) {
    var cell = event.target.closest('[data-g-filter-class]');
    if (cell) {
      var kind = cell.dataset.gFilterClass;
      filters.kind = kind && kind === filters.kind ? '' : kind;
      applyFilters();
      return;
    }
    var holder = event.target.closest('[data-g-filter-holder]');
    if (holder) {
      filters.holder = holder.dataset.gFilterHolder;
      applyFilters();
      return;
    }
    if (event.target.closest('#registry-reset')) {
      filters = { kind: '', holder: '' };
      applyFilters();
      return;
    }
    var range = event.target.closest('#chart-range [data-range]');
    if (range) {
      document.querySelectorAll('#chart-range [data-range]').forEach(function (b) {
        b.classList.toggle('is-active', b === range);
      });
      loadChart(parseInt(range.dataset.range, 10));
      return;
    }
    var gross = event.target.closest('#chart-gross-toggle');
    if (gross) {
      state.gross = !state.gross;
      gross.setAttribute('aria-pressed', state.gross ? 'true' : 'false');
      drawChart();
    }
  });

  document.addEventListener('g:panel-loaded', function (event) {
    if (event.target.querySelector('#chart-evolution')) {
      var hero = document.getElementById('hero');
      if (hero) state.currency = hero.dataset.currency;
      loadChart(state.range);
    }
  });
})();
