import { readdir, readFile } from "node:fs/promises";
import { gzipSync } from "node:zlib";
for (const name of (await readdir("dist/assets")).filter((n) => /\.(js|css)$/.test(n))) {
  const data = await readFile("dist/assets/" + name);
  console.log(
    `${name}: ${(data.length / 1000).toFixed(2)} kB; gzip ${(gzipSync(data).length / 1000).toFixed(2)} kB`,
  );
}
