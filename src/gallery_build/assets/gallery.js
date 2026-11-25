/* Static pages remain usable without JS. Navigation only enhances ordinary links. */
(() => {
  'use strict';
  const script = document.querySelector('script[src$="assets/gallery.js"]');
  const base = new URL('../', script.src);
  const views = window.GALLERY_VIEWS;
  const main = document.getElementById('gallery');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let busy = false;
  let pending = null;
  let mode = new URLSearchParams(location.search).get('mode') === 'collective' ? 'collective' : 'author';
  let switching = false;
  let queuedMode = null;
  let railPosition = 0;
  let activeFrame = 0;
  function revealSelectedTab() {
    const selected = document.querySelector('[data-mode][aria-pressed=true]');
    if (!selected) return;
    const nav = selected.parentElement;
    const right = selected.offsetLeft + selected.offsetWidth;
    if (right > nav.scrollLeft + nav.clientWidth) nav.scrollLeft = right - nav.clientWidth;
    if (selected.offsetLeft < nav.scrollLeft) nav.scrollLeft = selected.offsetLeft;
  }
  document.fonts.ready.then(revealSelectedTab);
  window.addEventListener('resize', revealSelectedTab);
  function activate(card) {
    if (!card || card.hidden || busy || switching) return;
    card.closest('.rail').querySelectorAll('.tablet').forEach(el => el.classList.toggle('is-active', el === card));
  }
  function activateNearest(rail) {
    cancelAnimationFrame(activeFrame);
    activeFrame = requestAnimationFrame(() => {
      const edge = rail.getBoundingClientRect().left + parseFloat(getComputedStyle(rail).paddingLeft);
      const cards = [...rail.querySelectorAll('.tablet:not([hidden])')];
      const nearest = cards.reduce((best, card) => !best || Math.abs(card.getBoundingClientRect().left-edge) < Math.abs(best.getBoundingClientRect().left-edge) ? card : best, null);
      activate(nearest);
    });
  }
  document.addEventListener('pointerover', event => {
    if (event.pointerType === 'mouse' && !event.buttons) activate(event.target.closest('.tablet'));
  });
  document.addEventListener('focusin', event => activate(event.target.closest('.tablet')));
  document.addEventListener('scroll', event => {
    if (event.target.matches?.('.rail')) activateNearest(event.target);
  }, {capture:true,passive:true});
  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
  const pathKey = () => Object.keys(views).find(key => new URL(views[key].path, base).pathname === location.pathname) || 'home';
  function applyMode(next) {
    mode = next;
    document.querySelectorAll('[data-mode]').forEach(el => el.setAttribute('aria-pressed', String(el.dataset.mode === mode)));
    document.querySelectorAll('[data-kind]').forEach(el => { el.hidden = el.dataset.kind !== mode; });
    const cards = [...document.querySelectorAll('.tablet:not([hidden])')];
    if (!cards.some(el => el.classList.contains('is-active'))) {
      document.querySelectorAll('.tablet').forEach(el => el.classList.toggle('is-active', el === cards[0]));
    }
    revealSelectedTab();
  }
  const visibleCards = () => [...document.querySelectorAll('.tablet:not([hidden])')].filter(el => {
    const r = el.getBoundingClientRect(); return r.right > 0 && r.left < innerWidth;
  });
  async function moveCards(direction) {
    if (reduced.matches) return;
    const animations = visibleCards().map((el, index) => {
      const distance = innerHeight - el.getBoundingClientRect().top + 40;
      const from = {transform:'translateY(0)', opacity:1};
      const below = {transform:`translateY(${distance}px)`, opacity:0};
      return el.animate(direction === 'out' ? [from, below] : [below, from], {
        duration:direction === 'out' ? 340 : 460, delay:Math.min(index, 6) * 55,
        easing:direction === 'out' ? 'cubic-bezier(.4,0,.8,.3)' : 'cubic-bezier(.16,1,.3,1)', fill:'both'
      });
    });
    await Promise.all(animations.map(a => a.finished.catch(() => {})));
    return animations;
  }
  async function switchMode(next) {
    if (busy) return;
    if (switching) {queuedMode = next; return;}
    if (next === mode) return;
    switching = true;
    const rail = document.querySelector('.rail');
    rail.inert = true;
    const tabs = [...document.querySelectorAll('[data-mode]')];
    document.querySelector('.modes').scrollLeft = 0;
    const before = tabs.map(el => ({rect:el.getBoundingClientRect(), opacity:getComputedStyle(el).opacity}));
    tabs.forEach(el => el.setAttribute('aria-pressed', String(el.dataset.mode === next)));
    if (!reduced.matches) tabs.forEach((el,index) => {
      const old = before[index], now = el.getBoundingClientRect();
      el.animate([{transform:`translate(${old.rect.left-now.left}px,${old.rect.top-now.top}px) scale(${old.rect.width/now.width})`,opacity:old.opacity},
                  {transform:'none',opacity:getComputedStyle(el).opacity}], {duration:420,easing:'cubic-bezier(.22,1,.36,1)'});
    });
    const outgoing = await moveCards('out');
    applyMode(next);
    outgoing?.forEach(a=>a.cancel());
    rail.scrollLeft = 0; railPosition = 0;
    const incoming = await moveCards('in');
    incoming?.forEach(a=>a.cancel());
    rail.inert = false;
    switching = false;
    if (queuedMode !== null) {const target=queuedMode;queuedMode=null;switchMode(target);}
  }
  async function navigate(key, historyAction = true) {
    if (!views[key] || switching) return;
    if (busy) { if (!historyAction) pending = key; return; }
    if (key === document.body.dataset.view) return;
    window.dispatchEvent(new Event("gallery:navigate"));
    busy = true;
    try {
      const rail = document.querySelector('.rail');
      if (rail) railPosition = rail.scrollLeft;
      const view = views[key];
      document.body.classList.remove('entering');
      const fromHome = document.body.dataset.view === 'home';
      document.body.classList.add(fromHome ? 'leaving-home' : 'leaving');
      document.body.style.backgroundColor = view.background;
      if (fromHome && !reduced.matches) {
        document.querySelectorAll('[data-mode]').forEach((el,index)=>el.animate(
          [{transform:'translateX(0)',opacity:getComputedStyle(el).opacity},{transform:`translateX(${-innerWidth}px)`,opacity:0}],
          {duration:440,delay:index*45,easing:'cubic-bezier(.55,0,1,.45)',fill:'forwards'}));
        await Promise.all([moveCards('out'),delay(500)]);
      } else if (!reduced.matches) await delay(430);
      const template = document.createElement('template');
      template.innerHTML = view.html;
      // Stored fragments use site-root-relative paths, compatible with Pages subpaths and preview bundles.
      template.content.querySelectorAll('[href],[src],[srcset]').forEach(el => {
        for (const attr of ['href','src','srcset']) {
          const value = el.getAttribute(attr);
          if (value && !/^https?:\/\//.test(value)) el.setAttribute(attr, new URL(value, base).href);
        }
      });
      main.replaceChildren(template.content);
      document.body.dataset.view = key;
      document.title = view.title;
      document.getElementById('custom-style').href = new URL(`assets/${key === 'home' ? 'empty' : 'custom-' + key}.css`, base).href;
      if (historyAction) {
        // Opaque sandbox previews cannot pushState; hash navigation remains isolated and supports Back.
        try { history.pushState({gallery: key}, '', new URL(view.path, base)); }
        catch { location.hash = `gallery=${encodeURIComponent(key)}`; }
      }
      applyMode(mode);
      window.scrollTo(0, 0);
      const nextRail = document.querySelector('.rail');
      if (nextRail) nextRail.scrollLeft = railPosition;
      document.body.classList.remove('leaving', 'leaving-home');
      document.body.classList.add('entering');
      main.focus({preventScroll:true});
      window.dispatchEvent(new Event("gallery:ready"));
    } finally {
      busy = false;
      if (pending !== null) { const key = pending; pending = null; navigate(key, false); }
    }
  }
  document.addEventListener('click', event => {
    const tab = event.target.closest('[data-mode]');
    if (tab) { switchMode(tab.dataset.mode); return; }
    const link = event.target.closest('a[data-view-link]');
    if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigate(link.dataset.viewLink);
  });
  const restore = () => {
    const match = location.hash.match(/^#gallery=([a-z0-9_-]+)$/);
    navigate(match ? match[1] : pathKey(), false);
  };
  window.addEventListener('popstate', restore);
  window.addEventListener('hashchange', restore);
  applyMode(mode);
  restore();
})();
