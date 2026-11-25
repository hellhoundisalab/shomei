/* Official players are loaded on demand. Opening a player never fakes playback. */
(() => {
  let dispose = () => {};
  const apis = new Map();
  function api(provider) {
    if (provider === 'youtube' && window.YT?.Player || provider === 'soundcloud' && window.SC?.Widget) return Promise.resolve();
    if (!apis.has(provider)) apis.set(provider, new Promise((resolve, reject) => {
      const script = document.createElement('script');
      const timer = setTimeout(() => reject(new Error('Player API timeout')), 10000);
      const ready = () => { clearTimeout(timer); resolve(); };
      if (provider === 'youtube') {window.onYouTubeIframeAPIReady = ready; script.src='https://www.youtube.com/iframe_api';}
      else {script.src='https://w.soundcloud.com/player/api.js'; script.onload=ready;}
      script.onerror = () => {clearTimeout(timer);reject(new Error('Player API unavailable'));};
      document.head.append(script);
    }));
    return apis.get(provider);
  }
  const icon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 18V5l12-2v13M9 8l12-2"/><ellipse cx="6" cy="18" rx="3" ry="2"/><ellipse cx="18" cy="16" rx="3" ry="2"/></svg>';
  function mount() {
    dispose();
    const host = document.querySelector('.music-mount');
    if (!host) return;
    const music = JSON.parse(host.dataset.music);
    host.innerHTML = '<div class="music-pill is-expanded"><button class="music-toggle" type="button" aria-label="Открыть музыкальный плеер" aria-expanded="false">' + icon + '</button><div class="music-details"><div class="music-track"><span class="music-title"></span><span class="music-artist"></span></div><a class="music-link" target="_blank" rel="noopener noreferrer" aria-label="Открыть музыку на сервисе">↗</a></div></div><section class="music-panel" aria-label="Музыкальный плеер" hidden><button type="button" class="music-close" aria-label="Закрыть и остановить плеер">×</button><div class="music-frame"></div><p class="music-notice"></p></section>';
    const pill = host.querySelector('.music-pill'), details = host.querySelector('.music-details'), button = host.querySelector('.music-toggle'), panel = host.querySelector('.music-panel'), target = host.querySelector('.music-frame');
    const title = host.querySelector('.music-title'), artist = host.querySelector('.music-artist');
    let controls = null, releasePlayer = () => {}, playing = false;
    function playback(value) {
      playing = value; pill.classList.toggle('is-playing', value);
      button.setAttribute('aria-label', controls ? (value ? 'Пауза' : 'Воспроизвести музыку') : 'Открыть музыкальный плеер');
      button.innerHTML = controls ? '<svg viewBox="0 0 24 24" aria-hidden="true">' + (value ? '<path d="M8 5v14M16 5v14"/>' : '<path d="m8 5 11 7-11 7Z"/>') + '</svg>' : icon;
    }
    title.textContent = music.title || ({track:'Композиция', song:'Композиция', album:'Альбом', playlist:'Плейлист'}[music.kind] || 'Музыка');
    artist.textContent = music.artist || music.name;
    title.title = title.textContent; artist.title = artist.textContent;
    host.querySelector('.music-link').href = music.url;
    let intro = true, hovered = false, touched = false, touchTimer;
    const update = () => { const open = intro || hovered || touched || pill.contains(document.activeElement) && document.activeElement.matches(':focus-visible') || !panel.hidden; pill.classList.toggle('is-expanded', open); details.inert = !open; details.setAttribute('aria-hidden', String(!open)); };
    const size = () => {
      const canvas = document.createElement('canvas').getContext('2d');
      const width = Math.max(...[title, artist].map(el => { canvas.font = getComputedStyle(el).font; return canvas.measureText(el.textContent).width; }));
      const mobile = matchMedia('(max-width:600px)').matches;
      pill.style.setProperty('--music-width', `${Math.max(mobile?144:155, Math.min(mobile?288:310, Math.ceil(width)+(mobile?126:138)))}px`);
    };
    size(); document.fonts.ready.then(() => {if(host.isConnected) size();});
    window.addEventListener('resize', size);
    pill.onpointerenter = e => {if(e.pointerType==='mouse'){hovered=true;update();}};
    pill.onpointerleave = e => {if(e.pointerType==='mouse'){hovered=false;update();}};
    pill.onpointerdown = e => {if(e.pointerType!=='mouse'){touched=true;clearTimeout(touchTimer);touchTimer=setTimeout(()=>{touched=false;update();},2500);update();}};
    pill.onfocusin = update; pill.onfocusout = () => requestAnimationFrame(update);
    const introTimer = setTimeout(() => {intro=false;update();},2000);
    function stop() { releasePlayer(); releasePlayer=()=>{}; controls=null; playback(false); target.replaceChildren(); }
    function close() { panel.hidden=true; stop(); button.setAttribute('aria-expanded','false'); update(); }
    button.onclick = () => {
      if (controls) {playing ? controls.pause() : controls.play(); return;}
      if (!panel.hidden) {close();return;}
      panel.hidden=false; button.setAttribute('aria-expanded','true'); update();
      host.querySelector('.music-notice').textContent = music.embed ? 'Запустите музыку в плеере. Сервис может требовать вход или ограничивать длительность.' : 'Не удалось загрузить встроенный плеер. Откройте музыку по ссылке ↗.';
      if (window.origin === 'null') {
        host.querySelector('.music-notice').textContent = 'Это защищённый предпросмотр. Проверьте воспроизведение в поле «Музыка» редактора заявки.';
        return;
      }
      if (music.embed) {
        const frame = document.createElement('iframe');
        const embed = new URL(music.embed);
        if (music.provider === 'youtube') {embed.searchParams.set('enablejsapi','1');embed.searchParams.set('origin',location.origin);}
        frame.src=embed.href; frame.title=`Плеер ${music.name}`; frame.allow='autoplay; encrypted-media; fullscreen; picture-in-picture'; frame.referrerPolicy='strict-origin-when-cross-origin'; target.append(frame);
        if (['youtube','soundcloud'].includes(music.provider)) api(music.provider).then(() => {
          if (!frame.isConnected || panel.hidden) return;
          if (music.provider === 'youtube') {
            const player = new YT.Player(frame, {events:{
              onReady: () => {if (!frame.isConnected) return;controls={play:()=>player.playVideo(),pause:()=>player.pauseVideo()};playback(false);},
              onStateChange: e => {if(frame.isConnected) playback(e.data===1);},
              onError: () => {controls=null;playback(false);}
            }});
            releasePlayer=()=>player.destroy();
          } else {
            const widget=SC.Widget(frame), events=SC.Widget.Events;
            widget.bind(events.READY,()=>{if (!frame.isConnected) return;controls={play:()=>widget.play(),pause:()=>widget.pause()};playback(false);});
            widget.bind(events.PLAY,()=>{if(frame.isConnected) playback(true);});
            for(const event of [events.PAUSE,events.FINISH,events.ERROR]) widget.bind(event,()=>{if(frame.isConnected) playback(false);});
            releasePlayer=()=>{for(const event of [events.READY,events.PLAY,events.PAUSE,events.FINISH,events.ERROR]) widget.unbind(event);};
          }
        }).catch(()=>{/* Official iframe controls remain available when its API is blocked. */});
      }
    };
    host.querySelector('.music-close').onclick = () => {close();button.focus();};
    const escape = e => {if(e.key==='Escape'&&!panel.hidden){close();button.focus();}};
    document.addEventListener('keydown', escape);
    dispose = () => {clearTimeout(introTimer);clearTimeout(touchTimer);window.removeEventListener('resize',size);document.removeEventListener('keydown',escape);stop();};
  }
  window.addEventListener('gallery:navigate', () => dispose());
  window.addEventListener('gallery:ready', mount);
  mount();
})();
