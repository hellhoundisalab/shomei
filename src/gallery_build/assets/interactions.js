/* Pointer controls enhance native links and touch scrolling. */
(() => {
  'use strict';
  let drag = null;
  let suppressClickUntil = 0;
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const hoverPointer = matchMedia('(any-hover: hover) and (any-pointer: fine)');
  let activePhoto = null, photoFrame = 0, photoPoint = null;
  function resetPhoto() {
    cancelAnimationFrame(photoFrame); photoFrame = 0;
    if (activePhoto) ['--hover-x','--hover-y','--hover-angle'].forEach(key => activePhoto.style.removeProperty(key));
    activePhoto = null;
  }
  document.addEventListener('pointermove', event => {
    const photo = event.target.closest('.stack img');
    if (!photo || event.pointerType !== 'mouse' || event.buttons || drag || reducedMotion.matches || !hoverPointer.matches || photo.closest('.rail').inert) {
      resetPhoto(); return;
    }
    if (activePhoto !== photo) {resetPhoto(); activePhoto = photo;}
    photoPoint = {x:event.clientX,y:event.clientY};
    if (photoFrame) return;
    photoFrame = requestAnimationFrame(() => {
      photoFrame = 0;
      // Measure the stationary stack, not the moving image: no hover feedback loop.
      const rect = photo.offsetParent.getBoundingClientRect();
      const clamp = value => Math.max(-1,Math.min(1,value));
      const x = clamp((photoPoint.x-rect.left-photo.offsetLeft)/photo.offsetWidth*2-1);
      const y = clamp((photoPoint.y-rect.top-photo.offsetTop)/photo.offsetHeight*2-1);
      photo.style.setProperty('--hover-x',`${x*4}px`);
      photo.style.setProperty('--hover-y',`${y*3}px`);
      photo.style.setProperty('--hover-angle',`${x*1.2}deg`);
    });
  }, {passive:true});
  document.addEventListener('pointerout', event => {if (event.target === activePhoto) resetPhoto();});
  document.addEventListener('pointerdown', resetPhoto, {passive:true});
  document.addEventListener('scroll', resetPhoto, {capture:true,passive:true});
  document.addEventListener('visibilitychange', () => {if (document.hidden) resetPhoto();});
  window.addEventListener('blur', resetPhoto);
  window.addEventListener('gallery:navigate', resetPhoto);
  reducedMotion.addEventListener('change', resetPhoto);
  hoverPointer.addEventListener('change', resetPhoto);
  document.addEventListener('wheel', event => {
    const rail = event.target.closest('.rail');
    if (!rail || rail.inert || event.ctrlKey || rail.scrollWidth <= rail.clientWidth) return;
    const delta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
    const unit = event.deltaMode === 1 ? 24 : event.deltaMode === 2 ? rail.clientWidth : 1;
    event.preventDefault();
    rail.scrollLeft += delta * unit;
  }, {passive:false});
  document.addEventListener('pointerdown', event => {
    const rail = event.target.closest('.rail');
    if (!rail || rail.inert || event.pointerType !== 'mouse' || event.button !== 0) return;
    drag = {rail, id:event.pointerId, x:event.clientX, scroll:rail.scrollLeft, moved:false};
  });
  document.addEventListener('pointermove', event => {
    if (!drag || drag.id !== event.pointerId) return;
    const delta = event.clientX - drag.x;
    if (!drag.moved && Math.abs(delta) < 6) return;
    if (!drag.moved) {
      drag.moved = true;
      drag.rail.classList.add('dragging');
      drag.rail.setPointerCapture(event.pointerId);
    }
    event.preventDefault();
    drag.rail.scrollLeft = drag.scroll - delta;
  }, {passive:false});
  function finishDrag(event) {
    if (!drag || drag.id !== event.pointerId) return;
    if (drag.moved) suppressClickUntil = performance.now() + 250;
    drag.rail.classList.remove('dragging');
    if (drag.rail.hasPointerCapture(event.pointerId)) drag.rail.releasePointerCapture(event.pointerId);
    drag = null;
  }
  document.addEventListener('pointerup', finishDrag);
  document.addEventListener('pointercancel', finishDrag);
  document.addEventListener('dragstart', event => {if (event.target.closest('.rail')) event.preventDefault();});
  document.addEventListener('click', event => {
    if (performance.now() < suppressClickUntil && event.target.closest('.rail')) {
      event.preventDefault(); event.stopImmediatePropagation();
    }
  }, true);

  const dialog = document.getElementById('photo-viewer');
  const image = document.getElementById('viewer-image');
  const stage = dialog.querySelector('.viewer-stage');
  const zoomLabel = document.getElementById('viewer-zoom');
  let zoom = 1, x = 0, y = 0, moved = false;
  const pointers = new Map();
  function paint() {
    const maxX = Math.max(0, (image.offsetWidth * zoom - stage.clientWidth + 32) / 2);
    const maxY = Math.max(0, (image.offsetHeight * zoom - stage.clientHeight) / 2);
    x = Math.max(-maxX, Math.min(maxX, x)); y = Math.max(-maxY, Math.min(maxY, y));
    image.style.transform = `translate(${x}px,${y}px) scale(${zoom})`;
    zoomLabel.value = `${Math.round(zoom * 100)}%`;
    stage.classList.toggle('zoomed', zoom > 1);
  }
  function reset() {zoom = 1; x = 0; y = 0; paint();}
  function zoomAt(next, clientX, clientY) {
    const rect = stage.getBoundingClientRect();
    const px = (clientX ?? rect.left + rect.width / 2) - rect.left - rect.width / 2;
    const py = (clientY ?? rect.top + rect.height / 2) - rect.top - rect.height / 2;
    next = Math.max(1, Math.min(5, next));
    x = px - (px - x) * next / zoom; y = py - (py - y) * next / zoom;
    zoom = next; paint();
  }
  document.addEventListener('click', event => {
    const link = event.target.closest('.photo-open');
    if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    image.src = link.href;
    image.alt = link.querySelector('img').alt;
    reset();
    dialog.showModal();
    document.body.classList.add('viewer-open');
    paint();
  });
  image.addEventListener('load', paint);
  dialog.addEventListener('close', () => {
    document.body.classList.remove('viewer-open');
    pointers.clear(); stage.classList.remove('panning'); reset();
  });
  dialog.addEventListener('click', event => {
    const action = event.target.closest('[data-viewer]')?.dataset.viewer;
    if (action === 'close') dialog.close();
    if (action === 'reset') reset();
    if (action === 'in') zoomAt(zoom * 1.25);
    if (action === 'out') zoomAt(zoom / 1.25);
    if (event.target === stage && !moved) dialog.close();
  });
  stage.addEventListener('wheel', event => {
    event.preventDefault();
    zoomAt(zoom * Math.exp(-event.deltaY * .002), event.clientX, event.clientY);
  }, {passive:false});
  stage.addEventListener('dblclick', event => {
    event.preventDefault();
    zoomAt(zoom > 1 ? 1 : 2, event.clientX, event.clientY);
  });
  const pinch = () => {
    const [a,b] = [...pointers.values()];
    return {distance:Math.hypot(b.x-a.x,b.y-a.y), x:(a.x+b.x)/2, y:(a.y+b.y)/2};
  };
  stage.addEventListener('pointerdown', event => {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    pointers.set(event.pointerId, {x:event.clientX,y:event.clientY});
    moved = false;
    stage.setPointerCapture(event.pointerId);
    if (zoom > 1) stage.classList.add('panning');
  });
  stage.addEventListener('pointermove', event => {
    const previous = pointers.get(event.pointerId);
    if (!previous) return;
    const oldPinch = pointers.size === 2 ? pinch() : null;
    const dx = event.clientX-previous.x, dy = event.clientY-previous.y;
    if (Math.abs(dx)+Math.abs(dy)>2) moved = true;
    pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});
    if (oldPinch) {
      const now = pinch();
      zoomAt(zoom * now.distance / Math.max(oldPinch.distance,1), now.x, now.y);
      x += now.x-oldPinch.x; y += now.y-oldPinch.y; paint();
    } else if (zoom>1) {x+=dx;y+=dy;paint();}
  });
  const release = event => {
    pointers.delete(event.pointerId);
    if (stage.hasPointerCapture(event.pointerId)) stage.releasePointerCapture(event.pointerId);
    if (!pointers.size) stage.classList.remove('panning');
  };
  stage.addEventListener('pointerup',release);stage.addEventListener('pointercancel',release);
  dialog.addEventListener('keydown',event=>{
    if (['+','=','-','0'].includes(event.key)) {
      event.preventDefault();
      if (event.key==='0') reset(); else zoomAt(zoom*(event.key==='-'? .8:1.25));
    }
  });
  window.addEventListener('resize',()=>{if(dialog.open) paint();});
  window.addEventListener('gallery:navigate',()=>{if(dialog.open) dialog.close();});
})();
