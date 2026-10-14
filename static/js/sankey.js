/* Glad sankey diagram for the household budget.
 *
 * The budget is two trees joined by a central node: the resources on the
 * left flow into the budget, which flows into the expenses and savings on the
 * right. As both sides are trees, the layout needs no crossing reduction:
 * each depth is a column, nodes are stacked in tree order and centred on
 * their parent, and every node has a single link towards the centre.
 *
 * Usage: GladSankey.render(element, payload, options) where payload is
 * {currency, center, others, total, left: [node], right: [node], regular}
 * and a node is {id, label, person, value, kind, source, children: [node]};
 * a non-empty person is shown in parentheses after the label. regular, when
 * set, is another {total, left, right} without the exceptional flows, shown
 * by setRegular(true).
 *
 * The diagram starts folded on the first level. Clicking a node or its link
 * folds or unfolds it, and the tooltip lists its content. Siblings smaller
 * than GROUP_SHARE of their parent, GROUP_MIN or more, are grouped in one
 * "others" node. Every node is at least MIN_HEIGHT high, and a parent at
 * least as high as its unfolded children, so a small group stays readable
 * once unfolded: the heights are proportional to the amounts only above
 * that. Colours come from the --g-* CSS tokens, so the diagram follows the
 * theme without being redrawn.
 */
(function () {
  'use strict';

  var SVG_NS = 'http://www.w3.org/2000/svg';
  var NODE_WIDTH = 10;
  var NODE_GAP = 10;
  var CHILD_GAP = 4;
  var MIN_HEIGHT = 14;
  var ROW_HEIGHT = 30;
  var GROUP_SHARE = 0.02;
  var GROUP_MIN = 3;
  var TIP_ROWS = 8;
  var PALETTE = ['c1', 'c2', 'c3', 'c4', 'c5', 'c6'];

  function el(name, attrs, parent) {
    var node = document.createElementNS(SVG_NS, name);
    Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, attrs[key]); });
    if (parent) parent.appendChild(node);
    return node;
  }

  function sum(nodes, value) {
    return nodes.reduce(function (s, n) { return s + value(n); }, 0);
  }

  function colorOf(node) {
    if (node.source === 'balance') return node.kind === 'saving' ? 'var(--g-pos)' : 'var(--g-neg)';
    return 'var(--g-' + node.color + ')';
  }

  /* The tree of a side with the small siblings grouped: GROUP_MIN or more
   * nodes below GROUP_SHARE of their parent become one "others" node,
   * placed before the balance. */
  function grouped(nodes, parentValue, parentId, label) {
    var small = nodes.filter(function (n) {
      return n.source !== 'balance' && n.value < parentValue * GROUP_SHARE;
    });
    if (small.length < GROUP_MIN) small = [];
    var out = [];
    nodes.forEach(function (n) {
      if (small.indexOf(n) < 0 && n.source !== 'balance') out.push(withGroups(n, label));
    });
    if (small.length) {
      out.push({
        id: parentId + ':others',
        label: label + ' (' + small.length + ')',
        person: '',
        kind: small[0].kind,
        source: 'others',
        value: sum(small, function (n) { return n.value; }),
        children: small.map(function (n) { return withGroups(n, label); }),
      });
    }
    nodes.forEach(function (n) { if (n.source === 'balance') out.push(withGroups(n, label)); });
    return out;
  }

  function withGroups(node, label) {
    var copy = Object.assign({}, node);
    copy.children = grouped(node.children || [], node.value, node.id, label);
    return copy;
  }

  /* Visible nodes of a side, with depth, parent and colour, in tree order. */
  function flatten(roots, side, expanded, colorOffset) {
    var out = [];
    function walk(node, depth, parent, color) {
      var item = {
        data: node, side: side, depth: depth, parent: parent, color: color,
        value: node.value, children: [],
        id: node.id, label: node.label, person: node.person, kind: node.kind, source: node.source,
        expandable: node.children.length > 0,
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

  /* Height of a node: proportional to its value, at least MIN_HEIGHT, and
   * enough for the links of its unfolded children. */
  function measure(node, scale) {
    var children = sum(node.children, function (c) { return measure(c, scale); });
    node.h = Math.max(MIN_HEIGHT, node.value * scale, children);
    return node.h;
  }

  function gapBefore(node, previous) {
    return node.parent && node.parent === previous.parent ? CHILD_GAP : NODE_GAP;
  }

  function columnHeight(nodes) {
    return nodes.reduce(function (s, n, i) { return s + n.h + (i ? gapBefore(n, nodes[i - 1]) : 0); }, 0);
  }

  /* Vertical positions: each column is stacked in tree order, the children of
   * a node are centred on it, then overlaps are pushed down and back up. */
  function placeColumn(nodes, height, anchor) {
    if (!nodes.length) return;
    var cursor = null;
    nodes.forEach(function (node) {
      var wanted = anchor(node);
      node.y = cursor === null ? Math.max(0, wanted) : Math.max(wanted, cursor.y + cursor.h + gapBefore(node, cursor));
      cursor = node;
    });
    if (cursor.y + cursor.h <= height) return;
    for (var i = nodes.length - 1; i >= 0; i--) {
      var node = nodes[i];
      var next = nodes[i + 1];
      node.y = Math.min(node.y, next ? next.y - gapBefore(next, node) - node.h : height - node.h);
    }
  }

  function childrenAnchor(node) {
    var parent = node.parent;
    var siblings = parent.children;
    var block = sum(siblings, function (s) { return s.h; }) + CHILD_GAP * (siblings.length - 1);
    var y = parent.y + parent.h / 2 - block / 2;
    for (var i = 0; i < siblings.length && siblings[i] !== node; i++) y += siblings[i].h + CHILD_GAP;
    return y;
  }

  /* Positions of the visible nodes of *trees* ({center, left, right}) in a
   * diagram *width* wide; the height grows when the minimum heights need it. */
  function layout(trees, expanded, width) {
    var left = flatten(trees.left, 'left', expanded, 0);
    var right = flatten(trees.right, 'right', expanded, trees.left.length);
    var leftDepth = maxDepth(left);
    var rightDepth = maxDepth(right);
    var leftRoots = left.filter(function (n) { return n.depth === 1; });
    var rightRoots = right.filter(function (n) { return n.depth === 1; });
    var total = Math.max(sum(leftRoots, function (n) { return n.value; }), sum(rightRoots, function (n) { return n.value; }));
    var center = { id: '__center', label: trees.center, value: total, shown: trees.total || total, depth: 0, side: 'center', children: [] };
    var columnCount = leftDepth + rightDepth + 1;
    var columns = [];
    for (var c = 0; c < columnCount; c++) columns.push([]);
    left.forEach(function (n) { n.column = leftDepth - n.depth; columns[n.column].push(n); });
    center.column = leftDepth;
    columns[leftDepth].push(center);
    right.forEach(function (n) { n.column = leftDepth + n.depth; columns[n.column].push(n); });

    var busiest = columns.reduce(function (m, column) { return Math.max(m, column.length); }, 1);
    var height = Math.max(320, Math.min(1100, busiest * ROW_HEIGHT));
    var scale = Infinity;
    columns.forEach(function (column) {
      var values = sum(column, function (n) { return n.value; });
      if (values > 0) scale = Math.min(scale, (height - NODE_GAP * (column.length - 1)) / values);
    });
    if (!isFinite(scale)) scale = 0;

    leftRoots.concat(rightRoots).forEach(function (root) { measure(root, scale); });
    var sides = [leftRoots, rightRoots].map(function (roots) { return sum(roots, function (n) { return n.h; }); });
    center.h = Math.max(total * scale, sides[0], sides[1]);
    center.offsets = { left: (center.h - sides[0]) / 2, right: (center.h - sides[1]) / 2 };
    columns.forEach(function (column) {
      if (column !== columns[leftDepth]) height = Math.max(height, columnHeight(column));
    });
    height = Math.ceil(Math.max(height, center.h));

    var step = columnCount > 1 ? (width - NODE_WIDTH) / (columnCount - 1) : 0;
    columns.forEach(function (column, index) {
      column.forEach(function (n) { n.x = index * step; });
    });

    center.y = (height - center.h) / 2;
    [left, right].forEach(function (side) {
      var roots = side.filter(function (n) { return n.depth === 1; });
      var top = (height - columnHeight(roots)) / 2;
      placeColumn(roots, height, function (node) {
        var y = top;
        for (var i = 0; i < roots.length && roots[i] !== node; i++) y += roots[i].h + NODE_GAP;
        return y;
      });
      for (var depth = 2; depth <= maxDepth(side); depth++) {
        placeColumn(side.filter(function (n) { return n.depth === depth; }), height, childrenAnchor);
      }
    });
    return { nodes: left.concat([center], right), center: center, total: total, height: height };
  }

  /* Links: every node flows to its parent (left) or from it (right). */
  function links(result) {
    // The centre receives the left links and sends the right ones: each side
    // of a node stacks its own links from the top, the centre's in its middle.
    var offsets = { left: new Map(), right: new Map() };
    function take(side, node, amount) {
      var start = node === result.center ? node.offsets[side] : 0;
      var used = offsets[side].has(node) ? offsets[side].get(node) : start;
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

  function expandableIds(nodes, out) {
    nodes.forEach(function (n) {
      if (n.children.length) {
        out.push(n.id);
        expandableIds(n.children, out);
      }
    });
    return out;
  }

  function render(container, data, options) {
    options = options || {};
    var locale = document.documentElement.lang || navigator.language;
    var money = new Intl.NumberFormat(locale, { style: 'currency', currency: data.currency, maximumFractionDigits: 0 });
    var percent = new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 1 });
    var state = { expanded: new Set(), monthly: !!options.monthly, regular: false };
    var views = {};

    container.classList.add('g-sankey');
    var tip = document.createElement('div');
    tip.className = 'g-sankey__tip';
    tip.hidden = true;

    function trees() {
      var key = state.regular && data.regular ? 'regular' : 'all';
      if (!views[key]) {
        var view = key === 'regular' ? data.regular : data;
        views[key] = {
          center: data.center,
          total: view.total,
          left: grouped(view.left, view.total, 'left', data.others),
          right: grouped(view.right, view.total, 'right', data.others),
        };
      }
      return views[key];
    }

    function amount(value) { return money.format(state.monthly ? value / 12 : value); }

    function nameWithPerson(parent, node) {
      var name = document.createElement('span');
      name.textContent = node.label;
      parent.appendChild(name);
      if (node.person) {
        var person = document.createElement('span');
        person.className = 'g-sankey__tip-person';
        person.textContent = ' (' + node.person + ')';
        parent.appendChild(person);
      }
    }

    function showTip(event, node, total) {
      tip.textContent = '';
      var title = document.createElement('strong');
      nameWithPerson(title, node);
      var value = document.createElement('span');
      value.textContent = amount(node.value) + (total ? ' · ' + percent.format(node.value / total) : '');
      tip.appendChild(title);
      tip.appendChild(value);
      var content = node.data.children.slice().sort(function (a, b) { return b.value - a.value; });
      if (content.length) {
        var list = document.createElement('ul');
        list.className = 'g-sankey__tip-list';
        content.slice(0, TIP_ROWS).forEach(function (child) {
          var row = document.createElement('li');
          var label = document.createElement('span');
          nameWithPerson(label, child);
          var figure = document.createElement('span');
          figure.textContent = amount(child.value);
          row.appendChild(label);
          row.appendChild(figure);
          list.appendChild(row);
        });
        if (content.length > TIP_ROWS && options.moreLabel) {
          var more = document.createElement('li');
          more.className = 'g-sankey__tip-more';
          more.textContent = options.moreLabel.replace('{n}', content.length - TIP_ROWS);
          list.appendChild(more);
        }
        tip.appendChild(list);
      }
      if (node.expandable) {
        var hint = document.createElement('small');
        hint.textContent = node.expanded ? (options.foldLabel || '') : (options.unfoldLabel || '');
        if (hint.textContent) tip.appendChild(hint);
      }
      tip.hidden = false;
      var box = container.getBoundingClientRect();
      var x = event.clientX - box.left + 12;
      var y = event.clientY - box.top + 12;
      tip.style.left = Math.max(4, Math.min(x, box.width - tip.offsetWidth - 4)) + 'px';
      tip.style.top = y + 'px';
    }

    function hideTip() { tip.hidden = true; }

    function toggle(node) {
      if (!node.expandable) return;
      if (state.expanded.has(node.id)) state.expanded.delete(node.id);
      else state.expanded.add(node.id);
      hideTip();
      draw();
      var again = container.querySelector('[data-node="' + CSS.escape(node.id) + '"]');
      if (again) again.focus();
    }

    function draw() {
      var width = Math.max(280, container.clientWidth);
      var result = layout(trees(), state.expanded, width);
      var height = result.height;

      container.textContent = '';
      var svg = el('svg', {
        width: width, height: height, viewBox: '0 0 ' + width + ' ' + height,
        role: 'img', 'aria-label': options.ariaLabel || data.center,
      });
      container.appendChild(svg);
      container.appendChild(tip);

      var linkLayer = el('g', { class: 'g-sankey__links' }, svg);
      links(result).forEach(function (link) {
        var path = el('path', { d: bandPath(link), class: 'g-sankey__link' + (link.node.expandable ? ' is-expandable' : '') }, linkLayer);
        path.style.fill = colorOf(link.node);
        path.addEventListener('mousemove', function (e) { showTip(e, link.node, result.total); });
        path.addEventListener('mouseleave', hideTip);
        if (link.node.expandable) path.addEventListener('click', function () { toggle(link.node); });
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
        if (node.person) {
          var person = el('tspan', { class: 'g-sankey__person', dx: 4 }, text);
          person.textContent = '(' + node.person + ')';
        }
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
      setRegular: function (regular) { state.regular = !!regular; draw(); },
      expandAll: function () {
        var current = trees();
        expandableIds(current.left.concat(current.right), []).forEach(function (id) { state.expanded.add(id); });
        draw();
      },
      collapseAll: function () { state.expanded.clear(); draw(); },
      destroy: function () { observer.disconnect(); container.textContent = ''; },
    };
  }

  window.GladSankey = { render: render, layout: layout, grouped: grouped };
})();
