// Deliberately narrow ZIP_STORED writer. No compression, ZIP64, extras or descriptors.
const table = new Uint32Array(256);
for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; table[n] = c; }
export async function crc32(blob) {
  let crc = 0xffffffff;
  for (let start = 0; start < blob.size; start += 1048576) {
    const bytes = new Uint8Array(await blob.slice(start, start + 1048576).arrayBuffer());
    for (const value of bytes) crc = table[(crc ^ value) & 255] ^ (crc >>> 8);
    await new Promise(resolve => setTimeout(resolve, 0));
  }
  return (crc ^ 0xffffffff) >>> 0;
}
export async function packageZip(manifest, photos) {
  const json = new Blob([JSON.stringify(manifest)], { type: 'application/json' });
  if (json.size > 64000 || photos.length !== manifest.photos.length) throw Error('Слишком большой текст заявки');
  const entries = [{ name: 'manifest.json', blob: json }, ...photos.map((photo, i) => ({ name: manifest.photos[i].file, blob: photo }))];
  const parts = [], directory = [];
  let offset = 0, directorySize = 0;
  for (const { name, blob } of entries) {
    if (!/^(manifest\.json|images\/\d{2}\.(jpg|png|webp))$/.test(name)) throw Error('Неверное имя файла');
    const encoded = new TextEncoder().encode(name), crc = await crc32(blob);
    const local = new Uint8Array(30 + encoded.length), l = new DataView(local.buffer);
    l.setUint32(0, 0x04034b50, true); l.setUint16(4, 20, true); l.setUint16(12, 33, true);
    l.setUint32(14, crc, true); l.setUint32(18, blob.size, true); l.setUint32(22, blob.size, true); l.setUint16(26, encoded.length, true); local.set(encoded, 30);
    const central = new Uint8Array(46 + encoded.length), c = new DataView(central.buffer);
    c.setUint32(0, 0x02014b50, true); c.setUint16(4, 20, true); c.setUint16(6, 20, true); c.setUint16(14, 33, true);
    c.setUint32(16, crc, true); c.setUint32(20, blob.size, true); c.setUint32(24, blob.size, true); c.setUint16(28, encoded.length, true); c.setUint32(42, offset, true); central.set(encoded, 46);
    parts.push(local, blob); directory.push(central); offset += local.length + blob.size; directorySize += central.length;
    if (offset + directorySize + 22 > 100000000) throw Error('Архив превышает 100 МБ. Удалите или уменьшите фотографию.');
  }
  const end = new Uint8Array(22), e = new DataView(end.buffer);
  e.setUint32(0, 0x06054b50, true); e.setUint16(8, entries.length, true); e.setUint16(10, entries.length, true); e.setUint32(12, directorySize, true); e.setUint32(16, offset, true);
  return new Blob([...parts, ...directory, end], { type: 'application/zip' });
}
