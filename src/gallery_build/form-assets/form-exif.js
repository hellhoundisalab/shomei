// Bounded technical metadata preview. The bot independently extracts/validates EXIF.
function tiff(bytes) {
  if (bytes.length < 8) return {};
  const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength), little = v.getUint16(0) === 0x4949;
  if (!little && v.getUint16(0) !== 0x4d4d) return {};
  const u16 = p => v.getUint16(p, little), u32 = p => v.getUint32(p, little), values = {};
  if (u16(2) !== 42) return {};
  const read = (offset, depth = 0) => {
    if (depth > 1 || offset + 2 > bytes.length) return;
    const count = u16(offset); if (count > 256 || offset + 2 + count * 12 > bytes.length) return;
    for (let i = 0; i < count; i++) {
      const p = offset + 2 + i * 12, tag = u16(p), type = u16(p + 2), n = u32(p + 4);
      if (tag === 0x8769) { read(u32(p + 8), depth + 1); continue; }
      if (![0x010f, 0x0110, 0x829a, 0x829d, 0x8827, 0x8833, 0x920a].includes(tag)) continue;
      const size = ({ 2: 1, 3: 2, 4: 4, 5: 8 })[type]; if (!size || n < 1 || n > 256) continue;
      const start = n * size <= 4 ? p + 8 : u32(p + 8); if (start + n * size > bytes.length) continue;
      if (type === 2) values[tag] = new TextDecoder().decode(bytes.slice(start, start + n)).replace(/\0/g, '').trim().slice(0, 200);
      if (type === 3) values[tag] = u16(start);
      if (type === 4) values[tag] = u32(start);
      if (type === 5 && u32(start + 4)) values[tag] = u32(start) / u32(start + 4);
    }
  };
  read(u32(4));
  const out = {}, camera = [values[0x010f], values[0x0110]].filter(Boolean).join(' ');
  if (camera) out.camera = camera;
  if (values[0x829d]) out.f_number = `f/${values[0x829d].toFixed(1)}`;
  if (values[0x829a]) out.exposure_time = (values[0x829a] < 1 ? `1/${Math.round(1 / values[0x829a])}` : values[0x829a]) + ' с';
  if (values[0x8827] || values[0x8833]) out.iso = String(values[0x8827] || values[0x8833]);
  if (values[0x920a]) out.focal_length = `${values[0x920a]} мм`;
  return out;
}
export async function imageInfo(file) {
  const bytes = new Uint8Array(await file.slice(0, 1048576).arrayBuffer()), view = new DataView(bytes.buffer);
  let ext, exif = {}, width, height;
  const ascii = (start, size) => String.fromCharCode(...bytes.slice(start, start + size));
  try {
    if (bytes[0] === 255 && bytes[1] === 216) {
      ext = 'jpg';
      for (let p = 2; p + 4 <= bytes.length;) {
        if (bytes[p] !== 255 || [0xda, 0xd9].includes(bytes[p + 1])) break;
        const marker = bytes[p + 1], length = view.getUint16(p + 2);
        if (length < 2 || p + 2 + length > bytes.length) break;
        if (marker === 0xe1 && ascii(p + 4, 6) === 'Exif\0\0') exif = tiff(bytes.slice(p + 10, p + 2 + length));
        if ([0xc0, 0xc1, 0xc2].includes(marker) && length >= 7) { height = view.getUint16(p + 5); width = view.getUint16(p + 7); }
        p += 2 + length;
      }
    } else if (ascii(1, 3) === 'PNG' && bytes[0] === 137) {
      ext = 'png'; width = view.getUint32(16); height = view.getUint32(20);
      for (let p = 8; p + 12 <= bytes.length;) { const size = view.getUint32(p); if (p + size + 12 > bytes.length) break; if (ascii(p + 4, 4) === 'eXIf') exif = tiff(bytes.slice(p + 8, p + 8 + size)); p += size + 12; }
    } else if (ascii(0, 4) === 'RIFF' && ascii(8, 4) === 'WEBP') {
      ext = 'webp';
      for (let p = 12; p + 8 <= bytes.length;) { const size = view.getUint32(p + 4, true); if (p + size + 8 > bytes.length) break; if (ascii(p, 4) === 'EXIF') { let start = p + 8; if (ascii(start, 6) === 'Exif\0\0') start += 6; exif = tiff(bytes.slice(start, p + 8 + size)); } p += 8 + size + (size % 2); }
    }
  } catch { /* Malformed metadata must not prevent a bounded image preview. */ }
  if (!ext) throw Error('Поддерживаются только JPEG, PNG и WebP');
  if (width * height > 40000000 || Math.max(width || 0, height || 0) > 20000) throw Error('Фото должно быть не больше 40 Мп и 20 000 px по стороне');
  return { ext, exif };
}
