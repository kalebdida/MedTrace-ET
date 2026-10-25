import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
function offlineShell(): Plugin {
  return {
    name: "offline-shell",
    generateBundle(_options, bundle) {
      const shell = new Set([
        "/",
        "/index.html",
        "/logo.svg",
        "/manifest.webmanifest",
        "/icon-192.png",
        "/icon-512.png",
      ]);
      const add = (name: string) => {
        if (shell.has("/" + name)) return;
        shell.add("/" + name);
        const item = bundle[name];
        if (item?.type === "chunk") item.imports.forEach(add);
      };
      for (const [name, item] of Object.entries(bundle)) {
        if (item.type === "chunk" && item.isEntry) add(name);
        if (name.endsWith(".css") && !name.includes("CloneMap")) shell.add("/" + name);
      }
      const version = Object.keys(bundle)
        .filter((k) => k.endsWith(".js"))
        .join("|");
      this.emitFile({
        type: "asset",
        fileName: "sw.js",
        source: `const CACHE='medtrace-'+${JSON.stringify(version)};const SHELL=${JSON.stringify([...shell])};self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL))));self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('medtrace-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(e.request.method!=='GET'||u.origin!==self.location.origin)return;if(e.request.mode==='navigate'){e.respondWith(fetch(e.request).catch(()=>caches.match('/index.html')));return;}if(!u.pathname.startsWith('/assets/')&&!SHELL.includes(u.pathname))return;e.respondWith(caches.match(e.request).then(hit=>hit||fetch(e.request).then(r=>{if(r.ok){const copy=r.clone();caches.open(CACHE).then(c=>c.put(e.request,copy));}return r;})));});`,
      });
    },
  };
}
export default defineConfig({
  plugins: [react(), offlineShell()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/testSetup.ts"],
    exclude: ["e2e/**", "node_modules/**"],
  },
});
