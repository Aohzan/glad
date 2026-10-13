/* Glad sankey diagram for the household budget.
 *
 * The budget is two trees joined by a central node: the resources on the
 * left flow into the budget, which flows into the expenses and savings on the
 * right. As both sides are trees, the layout needs no crossing reduction:
 * each depth is a column, nodes are stacked in tree order and centred on
 * their parent, and every node has a single link towards the centre.
 *
 * Usage: GladSankey.render(element, payload, {monthly: false}) where payload
 * is {currency, center, left: [node], right: [node]} and a node is
 * {id, label, value, kind, source, children: [node]}. Clicking a node with
 * children folds or unfolds it. Colours come from the --g-* CSS tokens, so
 * the diagram follows the theme without being redrawn.
 */
(function () {
  'use strict';

  var SVG_NS = 'http://www.w3.org/2000/svg';
  var NODE_WIDTH = 10;
  var NODE_GAP = 10;
  var CHILD_GAP = 4;
  var MIN_LABEL_HEIGHT = 9;
  var ROW_HEIGHT = 30;
  var PALETTE = ['c1', 'c2', 'c3', 'c4', 'c5', 'c6'];

  function el(name, attrs, parent) {
    var node = document.createElementNS(SVG_NS, name);
    Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, attrs[key]); });
    if (parent) parent.appendChild(node);
    return node;
  }

  function colorOf(node) {
    if (node.source === 'balance') return node.kind === 'saving' ? 'var(--g-pos)' : 'var(--g-neg)';
    return 'var(--g-' + node.color + ')';
  }

  /* Visible nodes of a side, with depth, parent and colour, in tree order. */
  function flatten(roots, side, expanded, colorOffset) {
    var out = [];
    function walk(node, depth, parent, color) {
      var item = {
        data: node, side: side, depth: depth, parent: parent, color: color,
        value: node.value, children: [],
        id: node.id, label: node.label, kind: node.kind, source: node.source,
        expandable: (node.children || []).length > 0,
        expanded: expanded.has(node.id),
      };
      out.push(item);
      if (parent) parent.children.push(item);
      if (item.expandable && item.expanded) {
        node.children.forEach(function (child) { walk(child, depth + 1, item, color); });
      }
    }
    roots.forEach(function (root, index) {
      walk(root, 1, null, PALETTE[(index + colorOffset) % PALETTE.length]);
    });
    return out;
  }

  function maxDepth(nodes) {
    return nodes.reduce(function (max, n) { return Math.max(max, n.depth); }, 0);
  }

  /* Vertical positions: each column is stacked in tree order, the children of
   * a node are centred on it, then overlaps are pushed down and back up. */
  function placeColumn(nodes, height, scale, anchor) {
    if (!nodes.length) return;
    nodes.forEach(function (node) { node.h = Math.max(1, node.value * scale); });
    var cursor = null;
    nodes.forEach(function (node) {
      var gap = cursor === null ? 0 : (node.parent && node.parent === cursor.parent ? CHILD_GAP : NODE_GAP);
      var wanted = anchor(node);
      node.y = cursor === null ? wanted : Math.max(wanted, cursor.y + cursor.h + gap);
      cursor = node;
    });
    var overflow = cursor.y + cursor.h - height;
    if (overflow > 0) {
      for (var i = nodes.length - 1; i >= 0; i--) {
        var node = nodes[i];
        var next = nodes[i + 1];
        var limit = next ? next.y - (next.parent === node.parent ? CHILD_GAP : NODE_GAP) - node.h : height - node.h;
        node.y = Math.min(node.y, limit);
      }
      var shift = Math.max(0, -nodes[0].y);
      nodes.forEach(function (n) { n.y += shift; });
    }
  }

  function childrenAnchor(node) {
    var parent = node.parent;
    var siblings = parent.children;
    var block = siblings.reduce(function (sum, s) { return sum + s.h; }, 0) + CHILD_GAP * (siblings.length - 1);
    var y = parent.y + parent.h / 2 - block / 2;
    for (var i = 0; i < siblings.length && siblings[i] !== node; i++) y += siblings[i].h + CHILD_GAP;
    return y;
  }

  function layout(state, width, height) {
    var left = flatten(state.data.left, 'left', state.expanded, 0);
    var right = flatten(state.data.right, 'right', state.expanded, state.data.left.length);
    var leftDepth = maxDepth(left);
    var rightDepth = maxDepth(right);
    var total = Math.max(
      left.filter(function (n) { return n.depth === 1; }).reduce(function (s, n) { return s + n.value; }, 0),
      right.filter(function (n) { return n.depth === 1; }).reduce(function (s, n) { return s + n.value; }, 0)
    );
    var center = { id: '__center', label: state.data.center, value: total, shown: state.data.total || total, depth: 0, side: 'center', children: [] };
    var columnCount = leftDepth + rightDepth + 1;
    var columns = [];
    for (var c = 0; c < columnCount; c++) columns.push([]);
    left.forEach(function (n) { n.column = leftDepth - n.depth; columns[n.column].push(n); });
    center.column = leftDepth;
    columns[leftDepth].push(center);
    right.forEach(function (n) { n.column = leftDepth + n.depth; columns[n.column].push(n); });

    var scale = Infinity;
    columns.forEach(function (column) {
      var sum = column.reduce(function (s, n) { return s + n.value; }, 0);
      if (sum > 0) scale = Math.min(scale, (height - NODE_GAP * (column.length - 1)) / sum);
    });
    if (!isFinite(scale)) scale = 0;

    var step = columnCount > 1 ? (width - NODE_WIDTH) / (columnCount - 1) : 0;
    columns.forEach(function (column, index) {
      column.forEach(function (n) { n.x = index * step; });
    });

    center.h = total * scale;
    center.y = (height - center.h) / 2;
    [left, right].forEach(function (side) {
      var roots = side.filter(function (n) { return n.depth === 1; });
      var block = roots.reduce(function (s, n) { return s + n.value * scale; }, 0) + NODE_GAP * Math.max(0, roots.length - 1);
      var top = (height - block) / 2;
      placeColumn(roots, height, scale, function (node) {
        var y = top;
        for (var i = 0; i < roots.length && roots[i] !== node; i++) y += roots[i].h + NODE_GAP;
        return y;
      });
      for (var depth = 2; depth <= maxDepth(side); depth++) {
        placeColumn(side.filter(function (n) { return n.depth === depth; }), height, scale, childrenAnchor);
      }
    });
    return { nodes: left.concat([center], right), center: center, total: total };
  }

  /* Links: every node flows to its parent (left) or from it (right). */
  function links(result) {
    // The centre receives the left links and sends the right ones: each side
    // of a node stacks its own links from the top.
    var offsets = { left: new Map(), right: new Map() };
    function take(side, node, amount) {
      var used = offsets[side].get(node) || 0;
      offsets[side].set(node, used + amount);
      return node.y + used;
    }
    var out = [];
    result.nodes.forEach(function (node) {
      if (node.side === 'center') return;
      var parent = node.parent || result.center;
      if (node.side === 'left') {
        out.push({ node: node, x0: node.x + NODE_WIDTH, y0: node.y, x1: parent.x, y1: take('left', parent, node.h), h: node.h });
      } else {
        out.push({ node: node, x0: parent.x + NODE_WIDTH, y0: take('right', parent, node.h), x1: node.x, y1: node.y, h: node.h });
      }
    });
    return out;
  }

  function bandPath(link) {
    var xm = (link.x0 + link.x1) / 2;
    return 'M' + link.x0 + ',' + link.y0 +
      'C' + xm + ',' + link.y0 + ' ' + xm + ',' + link.y1 + ' ' + link.x1 + ',' + link.y1 +
      'L' + link.x1 + ',' + (link.y1 + link.h) +
      'C' + xm + ',' + (link.y1 + link.h) + ' ' + xm + ',' + (link.y0 + link.h) + ' ' + link.x0 + ',' + (link.y0 + link.h) +
      'Z';
  }

  function render(container, data, options) {
    options = options || {};
    var locale = document.documentElement.lang || navigator.language;
    var money = new Intl.NumberFormat(locale, { style: 'currency', currency: data.currency, maximumFractionDigits: 0 });
    var percent = new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 1 });
    var state = { data: data, expanded: new Set(), monthly: !!options.monthly };
    var wide = container.clientWidth >= 720;
    if (wide) data.left.concat(data.right).forEach(function (root) { state.expanded.add(root.id); });

    container.classList.add('g-sankey');
    var tip = document.createElement('div');
    tip.className = 'g-sankey__tip';
    tip.hidden = true;

    function amount(value) { return money.format(state.monthly ? value / 12 : value); }

    function showTip(event, node, total) {
      tip.textContent = '';
      var title = document.createElement('strong');
      title.textContent = node.label;
      var value = document.createElement('span');
      value.textContent = amount(node.value) + (total ? ' · ' + percent.format(node.value / total) : '');
      tip.appendChild(title);
      tip.appendChild(value);
      if (node.expandable) {
        var hint = document.createElement('small');
        hint.textContent = node.expanded ? (options.foldLabel || '') : (options.unfoldLabel || '');
        if (hint.textContent) tip.appendChild(hint);
      }
      tip.hidden = false;
      var box = container.getBoundingClientRect();
      var x = event.clientX - box.left + 12;
      var y = event.clientY - box.top + 12;
      tip.style.left = Math.min(x, box.width - tip.offsetWidth - 4) + 'px';
      tip.style.top = y + 'px';
    }

    function hideTip() { tip.hidden = true; }

    function toggle(node) {
      if (!node.expandable) return;
      if (state.expanded.has(node.id)) state.expanded.delete(node.id);
      else state.expanded.add(node.id);
      draw();
      var again = container.querySelector('[data-node="' + CSS.escape(node.id) + '"]');
      if (again) again.focus();
    }

    function draw() {
      var width = Math.max(280, container.clientWidth);
      var probe = layout(state, width, 1000);
      var rows = {};
      probe.nodes.forEach(function (n) { rows[n.column] = (rows[n.column] || 0) + 1; });
      var busiest = Object.keys(rows).reduce(function (m, k) { return Math.max(m, rows[k]); }, 1);
      var height = options.height || Math.max(320, Math.min(1100, busiest * ROW_HEIGHT));
      var result = layout(state, width, height);

      container.textContent = '';
      var svg = el('svg', {
        width: width, height: height, viewBox: '0 0 ' + width + ' ' + height,
        role: 'img', 'aria-label': options.ariaLabel || data.center,
      });
      container.appendChild(svg);
      container.appendChild(tip);

      var linkLayer = el('g', { class: 'g-sankey__links' }, svg);
      links(result).forEach(function (link) {
        var path = el('path', { d: bandPath(link), class: 'g-sankey__link' }, linkLayer);
        path.style.fill = colorOf(link.node);
        path.addEventListener('mousemove', function (e) { showTip(e, link.node, result.total); });
        path.addEventListener('mouseleave', hideTip);
      });

      var nodeLayer = el('g', { class: 'g-sankey__nodes' }, svg);
      result.nodes.forEach(function (node) {
        var group = el('g', { class: 'g-sankey__node' + (node.expandable ? ' is-expandable' : '') }, nodeLayer);
        var rect = el('rect', { x: node.x, y: node.y, width: NODE_WIDTH, height: Math.max(1, node.h), rx: 2 }, group);
        rect.style.fill = node.side === 'center' ? 'var(--g-muted)' : colorOf(node);
        if (node.expandable) {
          group.setAttribute('tabindex', '0');
          group.setAttribute('role', 'button');
          group.setAttribute('aria-expanded', node.expanded ? 'true' : 'false');
          group.setAttribute('aria-label', node.label + ', ' + amount(node.value));
          group.setAttribute('data-node', node.id);
          group.addEventListener('click', function () { toggle(node); });
          group.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(node); }
          });
        }
        if (node.side !== 'center') {
          group.addEventListener('mousemove', function (e) { showTip(e, node, result.total); });
          group.addEventListener('mouseleave', hideTip);
        }
        if (node.h < MIN_LABEL_HEIGHT && node.side !== 'center') return;
        var toRight = node.side === 'left' || (node.side === 'center' && result.nodes.length === 1);
        var text = el('text', {
          x: node.side === 'center' ? node.x + NODE_WIDTH / 2 : (toRight ? node.x + NODE_WIDTH + 6 : node.x - 6),
          y: node.side === 'center' ? Math.max(14, node.y - 8) : node.y + node.h / 2,
          'text-anchor': node.side === 'center' ? 'middle' : (toRight ? 'start' : 'end'),
          'dominant-baseline': node.side === 'center' ? 'auto' : 'middle',
          class: 'g-sankey__label',
        }, group);
        var name = el('tspan', { class: 'g-sankey__name' }, text);
        name.textContent = (node.expandable ? (node.expanded ? '− ' : '+ ') : '') + node.label;
        var value = el('tspan', { class: 'g-sankey__value', dx: 6 }, text);
        value.textContent = amount(node.side === 'center' ? node.shown : node.value);
      });
    }

    draw();
    var lastWidth = container.clientWidth;
    var observer = new ResizeObserver(function () {
      if (Math.abs(container.clientWidth - lastWidth) < 2) return;
      lastWidth = container.clientWidth;
      draw();
    });
    observer.observe(container);

    return {
      setMonthly: function (monthly) { state.monthly = !!monthly; draw(); },
      destroy: function () { observer.disconnect(); container.textContent = ''; },
    };
  }

  window.GladSankey = { render: render, layout: layout };
})();
