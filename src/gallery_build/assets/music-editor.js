/* Shared author/review editor. Never execute pasted HTML or infer playback from load. */
(() => {
  const root = document.querySelector('[data-music-editor]');
  if (!root) return;
  const dock = root.closest('.music-editor-dock');
  if (dock) {
    const summary = dock.querySelector('summary'), panel = dock.querySelector('.music-popover');
    const reduced = matchMedia('(prefers-reduced-motion: reduce)');
    let expanded = dock.open, animation = null;
    summary.addEventListener('click', event => {
      event.preventDefault();
      expanded = !expanded;
      const from = dock.open ? {opacity:getComputedStyle(panel).opacity,transform:getComputedStyle(panel).transform} : {opacity:0,transform:'translateY(6px)'};
      animation?.cancel();
      dock.open = true;
      panel.inert = !expanded;
      if (!expanded && panel.contains(document.activeElement)) summary.focus();
      if (reduced.matches) { dock.open = expanded; animation = null; return; }
      const current = panel.animate([from, {opacity:expanded ? 1 : 0,transform:expanded ? 'translateY(0)' : 'translateY(6px)'}], {
        duration:expanded ? 180 : 140, easing:'ease-out', fill:'both'
      });
      animation = current;
      current.onfinish = () => {
        if (animation !== current) return;
        dock.open = expanded;
        current.cancel(); animation = null;
      };
    });
  }
  const url = root.querySelector('[name=music_url]'), title = root.querySelector('[name=music_title]'), artist = root.querySelector('[name=music_artist]');
  const stored = root.querySelector('[name=music_json]'), status = root.querySelector('[role=status]'), preview = root.querySelector('.music-preview');
  let music = null, player = null, generation = 0, timer, pending = Promise.resolve(), resolved = '', failure = '';
  let autoTitle = '', autoArtist = '';
  try { music = JSON.parse(stored.value || 'null'); } catch { /* Invalid initial data is rechecked. */ }
  const initialMusic = music;
  if (music) { url.value = music.url; title.value = music.title || ''; artist.value = music.artist || ''; }
  function save() { stored.value = JSON.stringify(music ? {...music, title:title.value.trim(), artist:artist.value.trim()} : null); }
  async function check() {
    const version = ++generation, value = url.value.trim();
    preview.replaceChildren(); music = null; player = null; resolved = ''; failure = ''; save();
    if (!value) { status.textContent = ''; return; }
    status.textContent = 'Распознаём ссылку…';
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const endpoint = new URL(root.dataset.resolver || 'https://admin.shomei.ru/music/resolve');
      endpoint.searchParams.set('url', value);
      const response = await fetch(endpoint, {credentials:'omit', signal:controller.signal});
      const data = await response.json();
      if (version !== generation) return;
      if (!response.ok || !data.player) throw new Error(data.error || 'Не удалось распознать ссылку');
      music = data.music; player = data.player; resolved = value;
      // An outage must not erase a previously resolved player while editing text.
      if (player.provider === 'bandcamp' && !music.bandcamp_id && initialMusic?.url === music.url && /^[1-9][0-9]{0,14}$/.test(initialMusic.bandcamp_id || '')) {
        music.bandcamp_id = initialMusic.bandcamp_id;
        player.embed = `https://bandcamp.com/EmbeddedPlayer/${player.kind}=${music.bandcamp_id}/size=large/bgcol=ffffff/linkcol=315d4e/artwork=small/transparent=true/`;
      }
      if (!title.value || title.value === autoTitle) title.value = autoTitle = music.title || '';
      if (!artist.value || artist.value === autoArtist) artist.value = autoArtist = music.artist || '';
      save();
      const link = document.createElement('a'); link.href = player.url; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = `Открыть в ${player.name} ↗`;
      preview.append(link);
      if (player.embed) {
        const frame = document.createElement('iframe'); frame.src = player.embed; frame.title = `Плеер ${player.name}`; frame.allow = 'autoplay; encrypted-media; fullscreen; picture-in-picture'; frame.referrerPolicy = 'strict-origin-when-cross-origin';
        frame.dataset.provider = player.provider;
        preview.append(frame);
      }
      status.textContent = `${player.name}. ${player.embed ? 'Проверьте воспроизведение в плеере.' : 'Плеер сейчас недоступен, сохранится ссылка на сервис.'} Доступность и длина отрывка зависят от сервиса, региона и аккаунта. Автозапуска нет.`;
    } catch (error) {
      if (version !== generation) return;
      failure = error.name === 'AbortError' ? 'Сервис не ответил. Повторите проверку или уберите ссылку.' : (error.message || 'Не удалось проверить музыку');
      status.textContent = failure;
    } finally { clearTimeout(timeout); }
  }
  function start() { clearTimeout(timer); pending = check(); return pending; }
  url.addEventListener('input', () => { ++generation; resolved = ''; clearTimeout(timer); timer = setTimeout(start, 600); });
  title.addEventListener('input', save); artist.addEventListener('input', save);
  root.querySelector('[data-check-music]').onclick = start;
  const read = async () => {
    if (url.value.trim() !== resolved) await start(); else await pending;
    if (failure) throw new Error(failure);
    save(); return JSON.parse(stored.value || 'null');
  };
  window.shomeiMusic = {read};
  root.closest('form')?.addEventListener('submit', async event => {
    if (!url.value.trim() || url.value.trim() === resolved) { save(); return; }
    event.preventDefault();
    try { await read(); root.closest('form').requestSubmit(); } catch { url.focus(); }
  });
  if (url.value) start();
})();
