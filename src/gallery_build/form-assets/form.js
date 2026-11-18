import { imageInfo } from './form-exif.js';
import { packageZip } from './form-zip.js';
const $ = id => document.getElementById(id);
const fields = [['camera', 'camera', 'Камера'], ['focal_length', 'focal', 'Фокусное расстояние'], ['f_number', 'aperture', 'Диафрагма'], ['exposure_time', 'shutter', 'Выдержка'], ['iso', 'iso', 'ISO']];
const fonts = { inter: "'Inter',sans-serif", georgia: 'Georgia,serif', playfair: "'Playfair Display',serif", montserrat: "'Montserrat',sans-serif", merriweather: "'Merriweather',serif", roboto_mono: "'Roboto Mono',monospace" };
const presets = [['Тёплый минимализм', '#faf7f2', '#c1622d', 'inter'], ['Тёмный контраст', '#121212', '#f2c744', 'montserrat'], ['Мягкая пастель', '#f5eef8', '#8e7cc3', 'georgia'], ['Чёрно-белая классика', '#ffffff', '#1a1a1a', 'georgia'], ['Природные тона', '#efeae0', '#3f6c51', 'playfair'], ['Ночной неон', '#0b0f19', '#00d1b2', 'roboto_mono']];
const photos = [];
let topic = null, busy = false, dirty = false, invalidTopic = false;
const message = (text, error = false) => { $('status').textContent = text; $('status').dataset.error = String(error); };
const resize = element => { element.style.height = 'auto'; element.style.height = `${element.scrollHeight}px`; };
function theme() {
  for (const key of ['background', 'accent']) {
    const input = $(key), valid = /^#[0-9a-fA-F]{6}$/.test(input.value);
    input.setCustomValidity(valid ? '' : 'Укажите цвет в формате #RRGGBB');
    if (!valid) return;
    $(`${key}-picker`).value = input.value;
    $(`${key}-swatch`).style.backgroundColor = input.value;
  }
  document.body.style.backgroundColor = $('background').value;
  document.body.style.setProperty('--ink', $('accent').value);
  document.body.style.setProperty('--accent', $('accent').value);
  document.body.style.setProperty('--body-font', fonts[$('font').value]);
  document.body.style.setProperty('--title-font', fonts[$('font').value]);
  const rgb = $('background').value.slice(1).match(/../g).map(x => parseInt(x, 16));
  document.querySelector('.exhibition').classList.toggle('dark', rgb.reduce((a, b) => a + b, 0) < 320);
  requestAnimationFrame(() => document.querySelectorAll('.editor-exhibition textarea').forEach(resize));
  document.querySelectorAll('.presets button').forEach((b, i) => b.setAttribute('aria-pressed', String(presets[i][1] === $('background').value.toLowerCase() && presets[i][2] === $('accent').value.toLowerCase())));
}
function maximum() { return topic ? Math.max(0, 5 - topic.used) : 20; }
function updateBudget() { $('budget').textContent = `${photos.length} / ${maximum()} · ${(photos.reduce((n, p) => n + p.file.size, 0) / 1000000).toFixed(1)} МБ`; }
const eye = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/><path class="eye-slash" d="m3 3 18 18"/></svg>';
function render() {
  $('photographs').replaceChildren();
  photos.forEach((photo, index) => {
    const figure = document.createElement('figure'); figure.className = `photograph has-exif ${photo.height > photo.width ? 'portrait' : ''}`;
    const image = new Image(); image.src = photo.preview; image.className = 'photo'; image.alt = photo.caption || `Фотография ${index + 1}`; image.width = photo.width; image.height = photo.height;
    const caption = document.createElement('figcaption'), input = document.createElement('input'); input.placeholder = 'Добавить подпись'; input.maxLength = 120; input.value = photo.caption; input.setAttribute('aria-label', `Подпись к фотографии ${index + 1}`); input.addEventListener('input', () => { photo.caption = input.value; dirty = true; }); caption.append(input);
    const actions = document.createElement('div'); actions.className = 'photo-actions';
    for (const [label, text, delta] of [['Выше', '↑', -1], ['Ниже', '↓', 1], ['Удалить фотографию', '×', 0]]) {
      const button = document.createElement('button'); button.type = 'button'; button.textContent = text; button.title = label; button.setAttribute('aria-label', `${label} ${index + 1}`); button.disabled = Boolean(delta && !photos[index + delta]);
      button.onclick = () => { if (busy) return; if (delta) [photos[index], photos[index + delta]] = [photos[index + delta], photos[index]]; else { URL.revokeObjectURL(photo.preview); photos.splice(index, 1); } dirty = true; render(); }; actions.append(button);
    }
    const exif = document.createElement('dl'); exif.className = 'exif';
    for (const [key, icon, label] of fields) {
      const row = document.createElement('div'), dt = document.createElement('dt'), dd = document.createElement('dd'), toggle = document.createElement('button'), iconImage = new Image();
      iconImage.src = `../assets/${icon}.svg`; iconImage.alt = label; dt.title = label; dt.append(iconImage); dd.textContent = photo.exif[key] || '—'; dd.title = photo.exif[key] ? label : `${label}: данные не найдены в предпросмотре`;
      toggle.disabled = topic?.exif_allowed === false; toggle.type = 'button'; toggle.className = 'exif-toggle'; toggle.innerHTML = eye; toggle.title = `Показывать: ${label}`; toggle.setAttribute('aria-label', `Показывать ${label} для фотографии ${index + 1}`);
      const sync = () => { const on = photo.visible.has(key); toggle.setAttribute('aria-pressed', String(on)); row.dataset.visible = String(on); }; sync();
      toggle.onclick = () => { if (photo.visible.has(key)) photo.visible.delete(key); else photo.visible.add(key); dirty = true; sync(); }; row.append(dt, dd, toggle); exif.append(row);
    }
    figure.append(image, caption, actions, exif); $('photographs').append(figure);
  });
  updateBudget();
}
async function preview(file) {
  const url = URL.createObjectURL(file), image = new Image();
  try {
    image.src = url; await image.decode();
    if (image.naturalWidth * image.naturalHeight > 40000000 || Math.max(image.naturalWidth, image.naturalHeight) > 20000) throw Error('Фото превышает 40 Мп или 20 000 px по стороне');
    const canvas = document.createElement('canvas'), scale = Math.min(1, 1600 / Math.max(image.naturalWidth, image.naturalHeight));
    canvas.width = Math.round(image.naturalWidth * scale); canvas.height = Math.round(image.naturalHeight * scale);
    canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', .86));
    if (!blob) throw Error('Не удалось подготовить изображение');
    const result = { preview: URL.createObjectURL(blob), width: image.naturalWidth, height: image.naturalHeight };
    canvas.width = canvas.height = 0; return result;
  } finally { image.src = ''; URL.revokeObjectURL(url); }
}
async function add(files) {
  if (busy) return;
  const config = files.find(f => f.name === 'shomei-topic.json');
  if (config) {
    if (photos.length || config.size > 64000) return message('Загрузите файл темы до фотографий; файл должен быть меньше 64 КБ.', true);
    try { loadTopic(JSON.parse(await config.text())); } catch { message('Не удалось прочитать файл темы.', true); }
    files = files.filter(f => f !== config);
  }
  if (invalidTopic) return;
  busy = true; $('export').disabled = true; const errors = [];
  for (const file of files) {
    try {
      if (photos.length >= maximum()) throw Error(`Доступно не более ${maximum()} фотографий`);
      if (!file.size || file.size > 30000000) throw Error('Фото должно быть не больше 30 МБ');
      if (photos.reduce((n, p) => n + p.file.size, 0) + file.size > 99930000 - (topic?.used_bytes || 0)) throw Error('Превышен объём заявки: 100 МБ с учётом архива');
      message(`Подготавливаю ${photos.length + 1}…`);
      const info = await imageInfo(file), display = await preview(file);
      photos.push({ file, ...info, ...display, caption: '', visible: new Set(topic?.exif_allowed === false ? [] : fields.map(x => x[0])) }); dirty = true;
    } catch (error) { errors.push(`${file.name || 'Изображение'}: ${error.message}`); }
  }
  render(); busy = false; $('export').disabled = invalidTopic; message(errors.join('\n'), errors.length > 0);
}
for (const key of ['background', 'accent']) {
  $(key).addEventListener('input', () => { theme(); dirty = true; });
  $(`${key}-picker`).addEventListener('input', event => { $(key).value = event.target.value; theme(); dirty = true; });
}
$('font').addEventListener('change', () => { theme(); dirty = true; });
for (const key of ['title', 'description', 'author', 'comment']) $(key).addEventListener('input', event => { if (event.target.tagName === 'TEXTAREA') resize(event.target); dirty = true; });
presets.forEach(([label, bg, accent, font]) => { const button = document.createElement('button'); button.type = 'button'; button.title = label; button.setAttribute('aria-label', label); button.style.setProperty('--preset-bg', bg); button.style.setProperty('--preset-accent', accent); button.onclick = () => { $('background').value = bg; $('accent').value = accent; $('font').value = font; theme(); dirty = true; }; document.querySelector('.presets').append(button); });
$('files').onchange = event => { add([...event.target.files]); event.target.value = ''; };
document.addEventListener('paste', event => { const files = [...(event.clipboardData?.files || [])]; if (files.length) { event.preventDefault(); add(files); } });
for (const type of ['dragenter', 'dragover']) $('drop').addEventListener(type, event => { event.preventDefault(); $('drop').classList.add('drag-over'); });
for (const type of ['dragleave', 'drop']) $('drop').addEventListener(type, event => { event.preventDefault(); $('drop').classList.remove('drag-over'); if (type === 'drop') add([...event.dataTransfer.files]); });
document.addEventListener('dragover', event => event.preventDefault()); document.addEventListener('drop', event => event.preventDefault());
$('drop').addEventListener('keydown', event => { if (event.target === $('drop') && ['Enter', ' '].includes(event.key)) { event.preventDefault(); $('files').click(); } });
document.addEventListener('click', event => document.querySelectorAll('.editor-toolbar details[open]').forEach(d => { if (!d.contains(event.target)) d.open = false; }));
window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
window.addEventListener('hashchange', () => location.reload());
window.addEventListener('resize', () => document.querySelectorAll('.editor-exhibition textarea').forEach(resize));
document.fonts.addEventListener('loadingdone', () => document.querySelectorAll('.editor-exhibition textarea').forEach(resize));
$('export').onclick = async () => {
  if (busy || invalidTopic) return;
  for (const id of ['title', 'author', 'background', 'accent']) if (!$(id).reportValidity()) return;
  if (!$('title').value.trim() || (!topic && !$('author').value.trim())) return message('Заполните название и имя автора', true);
  if (!photos.length) return message('Добавьте хотя бы одну фотографию', true);
  if (topic && Date.parse(topic.deadline) <= Date.now()) return message('Приём в эту выставку завершён. Выберите тему в боте заново.', true);
  busy = true; $('export').disabled = true; message('Собираю архив…');
  try {
    const manifest = { schema_version: 1, kind: topic ? 'collective' : 'author', topic_id: topic?.id || null, title: $('title').value.trim(), description: $('description').value.trim(), author: $('author').value.trim(), theme: { background: $('background').value, accent: $('accent').value, font: $('font').value }, comment: $('comment').value.trim(), photos: photos.map((p, i) => ({ file: `images/${String(i + 1).padStart(2, '0')}.${p.ext}`, caption: p.caption.trim(), exif_visible: [...p.visible].sort() })) };
    const blob = await packageZip(manifest, photos.map(p => p.file)), url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = 'shomei-application.zip'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 60000);
    dirty = false; message('Архив скачан. Отправьте его боту файлом и подтвердите заявку.'); $('export-done').showModal();
  } catch (error) { message(error.message, true); }
  finally { busy = false; $('export').disabled = false; }
};
$('close-export').onclick = () => $('export-done').close();
function loadTopic(value) {
  document.body.dataset.kind = 'collective';
  try {
    invalidTopic = false;
    if (!/^COL-[A-F0-9]{16}$/.test(value.id) || typeof value.title !== 'string' || !value.title.trim() || value.title.length > 300 || typeof value.description !== 'string' || value.description.length > 10000 || !fonts[value.font] || !/^#[a-f0-9]{6}$/i.test(value.background) || !/^#[a-f0-9]{6}$/i.test(value.accent) || !Number.isInteger(value.used) || value.used < 0 || value.used > 5 || !Number.isFinite(Date.parse(value.deadline)) || !Number.isInteger(value.used_bytes ?? 0) || (value.used_bytes ?? 0) < 0 || (value.used_bytes ?? 0) > 100000000) throw Error();
    message(''); topic = value; $('title').value = value.title; $('description').value = value.description; $('title').readOnly = $('description').readOnly = true; $('title').maxLength = 300; $('description').maxLength = 10000;
    if (value.font === 'merriweather' && !$('font').querySelector('option[value=merriweather]')) $('font').add(new Option('Merriweather', 'merriweather'));
    $('background').value = value.background; $('accent').value = value.accent; $('font').value = value.font;
    $('font').disabled = true; for (const node of $('colors').querySelectorAll('input,button')) node.disabled = true;
    $('author').required = false; $('author').placeholder = 'Имя (необязательно)';
    $('mode-hint').textContent = `Общая выставка · до ${new Date(value.deadline).toLocaleString('ru-RU')} · осталось ${maximum()} фото. Название и оформление задаёт администратор.`;
    if (!maximum() || Date.parse(value.deadline) <= Date.now()) { invalidTopic = true; message('Приём завершён или уже загружены все 5 фото. Проверьте тему в боте.', true); }
  } catch { invalidTopic = true; message('Ссылка на общую выставку повреждена. Откройте форму заново из бота.', true); }
  $('export').disabled = invalidTopic; theme(); updateBudget();
}
const params = new URLSearchParams(location.hash.slice(1));
if (params.has('topic') || params.has('collective')) document.body.dataset.kind = 'collective';
if (params.has('topic')) {
  try {
    const raw = params.get('topic'); if (raw.length > 30000) throw Error();
    loadTopic(JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(raw.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0)))));
  } catch { invalidTopic = true; message('Ссылка повреждена. Откройте её заново из бота.', true); }
} else if (params.has('collective')) { invalidTopic = true; message('Сначала добавьте файл shomei-topic.json, полученный в боте.'); }
$('export').disabled = invalidTopic;
$('date').textContent = new Date().toLocaleDateString('ru-RU'); theme(); updateBudget();
