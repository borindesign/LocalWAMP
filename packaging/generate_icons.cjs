// Build-only dependency: npm install --no-save sharp (or expose it via NODE_PATH).
const fs = require('node:fs/promises');
const path = require('node:path');
const sharp = require('sharp');

async function main() {
  const root = path.resolve(__dirname, '..');
  const svg = await fs.readFile(path.join(root, 'assets', 'localwamp.svg'));
  const sizes = [16, 24, 32, 48, 64, 128, 256];
  const images = await Promise.all(sizes.map(size => sharp(svg, { density: 384 })
    .resize(size, size).png().toBuffer()));
  const directory = Buffer.alloc(6 + images.length * 16);
  directory.writeUInt16LE(1, 2);
  directory.writeUInt16LE(images.length, 4);
  let offset = directory.length;
  images.forEach((png, index) => {
    const entry = 6 + index * 16;
    directory[entry] = directory[entry + 1] = sizes[index] === 256 ? 0 : sizes[index];
    directory.writeUInt16LE(1, entry + 4);
    directory.writeUInt16LE(32, entry + 6);
    directory.writeUInt32LE(png.length, entry + 8);
    directory.writeUInt32LE(offset, entry + 12);
    offset += png.length;
  });
  const ico = Buffer.concat([directory, ...images]);
  await fs.writeFile(path.join(root, 'assets', 'localwamp.ico'), ico);
  await sharp(svg, { density: 384 }).resize(512, 512).png()
    .toFile(path.join(root, 'assets', 'localwamp.png'));
  const website = path.join(root, 'website');
  try {
    await fs.access(website);
    await fs.copyFile(path.join(root, 'assets', 'localwamp.svg'), path.join(website, 'assets', 'img', 'localwamp.svg'));
    await fs.writeFile(path.join(website, 'favicon.ico'), ico);
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  console.log('Generated LocalWAMP PNG and Windows ICO (16–256 px).');
}

main().catch(error => { console.error(error); process.exitCode = 1; });
