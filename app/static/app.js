function csrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.content : '';
}

function fmtNum(n) {
  return Number(n).toLocaleString('en-US', { maximumFractionDigits: 2 });
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

async function doTick(el) {
  if (el.classList.contains('busy') || el.classList.contains('future')) return;
  el.classList.add('busy');
  try {
    const resp = await fetch('/tick', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken()
      },
      body: JSON.stringify({
        child_id: parseInt(el.dataset.child, 10),
        task_id: parseInt(el.dataset.task, 10),
        date: el.dataset.date
      })
    });
    if (!resp.ok) {
      const data = await resp.json().catch(function () { return {}; });
      alert(data.error || '操作失败，请重试');
      return;
    }
    const data = await resp.json();
    applyTick(el, data);
  } catch (e) {
    alert('网络错误，请重试');
  } finally {
    el.classList.remove('busy');
  }
}

function applyTick(el, data) {
  el.classList.toggle('done', !!data.done);
  // week table cell: keep the check mark in sync without a page refresh
  if (el.classList.contains('cell')) el.textContent = data.done ? '✓' : '';

  setText('today-total', fmtNum(data.today_total));
  setText('today-count', String(data.today_count));
  setText('balance', fmtNum(data.balance));

  document.querySelectorAll('[data-day-total]').forEach(function (node) {
    const v = data.day_totals[node.dataset.dayTotal];
    node.textContent = v ? fmtNum(v) : '';
  });
  document.querySelectorAll('[data-strip-total]').forEach(function (node) {
    const v = data.day_totals[node.dataset.stripTotal];
    if (v === undefined) return; // strip 跨周，不在本周数据里的日期保持原样
    node.textContent = v ? fmtNum(v) : '—';
    node.classList.toggle('has-score', !!v);
  });
  document.querySelectorAll('[data-task-score]').forEach(function (node) {
    const info = data.task_week[node.dataset.taskScore];
    if (info) node.textContent = info.days ? fmtNum(info.score) : '';
  });
  document.querySelectorAll('[data-task-days]').forEach(function (node) {
    const info = data.task_week[node.dataset.taskDays];
    if (info) node.textContent = info.days;
  });

  const dayTotals = Object.values(data.day_totals || {});
  const weekScore = dayTotals.reduce(function (a, b) { return a + b; }, 0);
  const weekDays = dayTotals.filter(function (v) { return v > 0; }).length;
  setText('week-total', weekScore ? fmtNum(weekScore) : '');
  setText('week-score', fmtNum(weekScore));
  setText('week-days', weekDays);

  const s = data.settlement;
  if (s) {
    setText('set-opening', fmtNum(s.opening));
    setText('set-earned', fmtNum(s.earned));
    setText('set-available', fmtNum(s.available));
    setText('set-spent', fmtNum(s.spent));
    setText('set-carry', fmtNum(s.carry));
  }
}

function switchChild(sel) {
  const url = new URL(window.location.href);
  url.searchParams.set('child', sel.value);
  window.location.href = url.toString();
}

function navPanel() {
  return document.querySelector('.topbar');
}

function setNavOpen(open) {
  const topbar = navPanel();
  const toggle = document.querySelector('[data-nav-toggle]');
  if (!topbar || !toggle) return;
  topbar.classList.toggle('open', open);
  toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
}

document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('[data-tick]').forEach(function (el) {
    el.addEventListener('click', function () { doTick(el); });
  });
  document.querySelectorAll('select[data-switch-child]').forEach(function (sel) {
    sel.addEventListener('change', function () { switchChild(sel); });
  });

  const toggle = document.querySelector('[data-nav-toggle]');
  if (toggle) {
    toggle.addEventListener('click', function (e) {
      e.stopPropagation();
      const topbar = navPanel();
      setNavOpen(!(topbar && topbar.classList.contains('open')));
    });
    document.addEventListener('click', function (e) {
      const topbar = navPanel();
      if (topbar && topbar.classList.contains('open') && !topbar.contains(e.target)) {
        setNavOpen(false);
      }
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') setNavOpen(false);
    });
    document.querySelectorAll('.nav a').forEach(function (link) {
      link.addEventListener('click', function () { setNavOpen(false); });
    });
  }

  setTimeout(function () {
    document.querySelectorAll('.flash').forEach(function (f) { f.classList.add('hide'); });
  }, 4000);
});
