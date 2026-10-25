import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { useI18n } from "./i18n";

function drawFrontTexture(state: "genuine" | "clone"): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 680;
  const ctx = canvas.getContext("2d")!;

  // Cardstock base
  ctx.fillStyle = "#f9faf6";
  ctx.fillRect(0, 0, 512, 680);

  // Subtle clinical border
  ctx.strokeStyle = state === "genuine" ? "#b7d4cb" : "#f2b8b5";
  ctx.lineWidth = 6;
  ctx.strokeRect(12, 12, 488, 656);

  // Top clinical header band
  ctx.fillStyle = state === "genuine" ? "#0b4f4a" : "#8c1d24";
  ctx.fillRect(12, 12, 488, 118);

  // Brand & Rx mark
  ctx.fillStyle = "#ffffff";
  ctx.font = "700 26px system-ui, sans-serif";
  ctx.fillText("MEDTRACE-ET", 36, 62);
  ctx.font = "500 17px ui-monospace, monospace";
  ctx.fillStyle = state === "genuine" ? "#99f6e4" : "#fecaca";
  ctx.fillText("EFDA SERIALIZED PACK · RX", 36, 98);

  // Clinical cross badge
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(428, 42, 42, 14);
  ctx.fillRect(442, 28, 14, 42);

  // Medicine title & dosage block
  ctx.fillStyle = "#112421";
  ctx.font = "800 32px system-ui, sans-serif";
  ctx.fillText("AMOXICILLIN 500mg", 36, 186);
  ctx.fillStyle = "#49615c";
  ctx.font = "600 20px system-ui, sans-serif";
  ctx.fillText("30 Hard Capsules · Oral Use", 36, 220);

  // Accent divider
  ctx.fillStyle = state === "genuine" ? "#0d9488" : "#dc2626";
  ctx.fillRect(36, 242, 440, 5);

  // GS1 DataMatrix Plate Container
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(36, 274, 236, 236);
  ctx.strokeStyle = state === "genuine" ? "#0b4f4a" : "#dc2626";
  ctx.lineWidth = 4;
  ctx.strokeRect(36, 274, 236, 236);

  // Draw 14x14 GS1 DataMatrix with L-finder and timing pattern
  const grid = 14;
  const cell = 13;
  const startX = 63;
  const startY = 301;
  ctx.fillStyle = "#0f1e1c";
  for (let r = 0; r < grid; r++) {
    for (let c = 0; c < grid; c++) {
      const isLeftFinder = c === 0;
      const isBottomFinder = r === grid - 1;
      const isTopTiming = r === 0 && c % 2 === 0;
      const isRightTiming = c === grid - 1 && r % 2 === 1;
      const isDataBit =
        r > 0 &&
        r < grid - 1 &&
        c > 0 &&
        c < grid - 1 &&
        ((r * 7 + c * 13 + (r ^ c)) % 3 === 0 || (r + c) % 5 === 0);
      if (isLeftFinder || isBottomFinder || isTopTiming || isRightTiming || isDataBit) {
        ctx.fillRect(startX + c * cell, startY + r * cell, cell - 1, cell - 1);
      }
    }
  }

  // Right side GS1 human-readable AI fields
  ctx.fillStyle = "#49615c";
  ctx.font = "700 15px ui-monospace, monospace";
  ctx.fillText("(01) GTIN", 292, 304);
  ctx.fillStyle = "#112421";
  ctx.font = "700 17px ui-monospace, monospace";
  ctx.fillText("09506000134352", 292, 328);

  ctx.fillStyle = "#49615c";
  ctx.font = "700 15px ui-monospace, monospace";
  ctx.fillText("(21) SERIAL", 292, 368);
  ctx.fillStyle = state === "genuine" ? "#0b4f4a" : "#b91c1c";
  ctx.font = "700 18px ui-monospace, monospace";
  ctx.fillText("DEMO0001", 292, 392);

  ctx.fillStyle = "#49615c";
  ctx.font = "700 15px ui-monospace, monospace";
  ctx.fillText("(10) BATCH   (17) EXP", 292, 432);
  ctx.fillStyle = "#112421";
  ctx.font = "700 17px ui-monospace, monospace";
  ctx.fillText("BATCH42      2030-12", 292, 456);

  // Bottom status banner on box face
  ctx.fillStyle = state === "genuine" ? "#e6f6f1" : "#fee2e2";
  ctx.fillRect(36, 540, 440, 96);
  ctx.strokeStyle = state === "genuine" ? "#0d9488" : "#dc2626";
  ctx.lineWidth = 3;
  ctx.strokeRect(36, 540, 440, 96);

  ctx.strokeStyle = state === "genuine" ? "#065f46" : "#991b1b";
  ctx.lineWidth = 4.5;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  if (state === "genuine") {
    ctx.moveTo(56, 577);
    ctx.lineTo(65, 586);
    ctx.lineTo(80, 568);
  } else {
    ctx.moveTo(58, 567);
    ctx.lineTo(78, 587);
    ctx.moveTo(78, 567);
    ctx.lineTo(58, 587);
  }
  ctx.stroke();

  ctx.fillStyle = state === "genuine" ? "#065f46" : "#991b1b";
  ctx.font = "800 26px system-ui, sans-serif";
  ctx.fillText(state === "genuine" ? "GENUINE · PASS" : "CLONE DETECTED · FAIL", 92, 586);
  ctx.font = "600 16px ui-monospace, monospace";
  ctx.fillText(
    state === "genuine"
      ? "AUDIT SEQ #1 · PH-ADAMA-001 · VERIFIED"
      : "IMPOSSIBLE TRAVEL · 291 KM IN 50 MIN",
    58,
    616,
  );

  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function drawSideTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 512;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#eff3ef";
  ctx.fillRect(0, 0, 256, 512);
  ctx.fillStyle = "#0b4f4a";
  ctx.fillRect(0, 0, 256, 86);
  ctx.fillStyle = "#49615c";
  for (let y = 130; y < 440; y += 22) {
    ctx.fillRect(36, y, y % 44 === 0 ? 180 : 130, 8);
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

export function StaticPackSvg({ state = "genuine" }: { state?: "genuine" | "clone" }) {
  const isClone = state === "clone";
  return (
    <div className="hero-svg-fallback" data-testid="pack-svg-fallback">
      <svg
        viewBox="0 0 360 300"
        role="img"
        aria-label="GS1 DataMatrix medicine pack scanner illustration"
        className="pack-svg"
      >
        <defs>
          <linearGradient id="packBg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={isClone ? "#2a1215" : "#0b2926"} />
            <stop offset="100%" stopColor={isClone ? "#1a0c0e" : "#071a18"} />
          </linearGradient>
          <linearGradient id="laserGlow" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={isClone ? "#ef4444" : "#14b8a6"} stopOpacity="0" />
            <stop offset="50%" stopColor={isClone ? "#f87171" : "#2dd4bf"} stopOpacity="1" />
            <stop offset="100%" stopColor={isClone ? "#ef4444" : "#14b8a6"} stopOpacity="0" />
          </linearGradient>
        </defs>
        <rect width="360" height="300" rx="18" fill="url(#packBg)" />
        {/* Grid lines */}
        <g stroke={isClone ? "#fca5a522" : "#5eead422"} strokeWidth="1">
          <line x1="0" y1="60" x2="360" y2="60" />
          <line x1="0" y1="150" x2="360" y2="150" />
          <line x1="0" y1="240" x2="360" y2="240" />
          <line x1="90" y1="0" x2="90" y2="300" />
          <line x1="180" y1="0" x2="180" y2="300" />
          <line x1="270" y1="0" x2="270" y2="300" />
        </g>
        {/* Isometric 3D Medicine Carton */}
        <g transform="translate(88, 30)">
          {/* Side depth panel */}
          <polygon points="168,18 194,6 194,214 168,228" fill="#dbe4de" stroke="#8da399" />
          {/* Top flap */}
          <polygon
            points="0,18 26,6 194,6 168,18"
            fill={isClone ? "#991b1b" : "#0f766e"}
            stroke="#5eead4"
          />
          {/* Front carton face */}
          <rect
            x="0"
            y="18"
            width="168"
            height="210"
            rx="4"
            fill="#f8faf7"
            stroke={isClone ? "#ef4444" : "#14b8a6"}
            strokeWidth="2"
          />
          {/* Top header bar */}
          <rect
            x="0"
            y="18"
            width="168"
            height="38"
            rx="3"
            fill={isClone ? "#991b1b" : "#0b4f4a"}
          />
          <text x="14" y="41" fill="#ffffff" fontSize="11" fontWeight="800" fontFamily="monospace">
            MEDTRACE-ET · RX
          </text>
          {/* Cross */}
          <path d="M142 30 h6 v-6 h6 v6 h6 v6 h-6 v6 h-6 v-6 h-6 z" fill="#ffffff" />
          {/* Title */}
          <text x="14" y="76" fill="#112421" fontSize="12" fontWeight="800" fontFamily="sans-serif">
            AMOXICILLIN 500mg
          </text>
          <text x="14" y="92" fill="#52645f" fontSize="9" fontFamily="monospace">
            GTIN 09506000134352
          </text>
          {/* GS1 DataMatrix */}
          <g transform="translate(14, 104)">
            <rect
              x="0"
              y="0"
              width="68"
              height="68"
              fill="#ffffff"
              stroke="#0b4f4a"
              strokeWidth="1.5"
            />
            {/* L finder */}
            <rect x="6" y="6" width="6" height="56" fill="#0f1e1c" />
            <rect x="6" y="56" width="56" height="6" fill="#0f1e1c" />
            {/* Data cells */}
            <rect x="18" y="12" width="8" height="8" fill="#0f1e1c" />
            <rect x="34" y="12" width="8" height="8" fill="#0f1e1c" />
            <rect x="50" y="12" width="8" height="8" fill="#0f1e1c" />
            <rect x="26" y="24" width="14" height="8" fill="#0f1e1c" />
            <rect x="46" y="24" width="12" height="12" fill="#0f1e1c" />
            <rect x="16" y="36" width="12" height="12" fill="#0f1e1c" />
            <rect x="34" y="40" width="18" height="10" fill="#0f1e1c" />
          </g>
          {/* Serial & Batch */}
          <text x="90" y="122" fill="#52645f" fontSize="8" fontFamily="monospace">
            (21) SERIAL
          </text>
          <text x="90" y="135" fill="#0b4f4a" fontSize="10" fontWeight="700" fontFamily="monospace">
            DEMO0001
          </text>
          <text x="90" y="154" fill="#52645f" fontSize="8" fontFamily="monospace">
            (10) BATCH42
          </text>
          <text x="90" y="167" fill="#52645f" fontSize="8" fontFamily="monospace">
            (17) 2030-12-31
          </text>
          {/* Verdict pill on box */}
          <rect
            x="14"
            y="186"
            width="140"
            height="28"
            rx="6"
            fill={isClone ? "#fee2e2" : "#dcfce7"}
            stroke={isClone ? "#dc2626" : "#059669"}
          />
          <path
            d={isClone ? "M22 196 l8 8 M30 196 l-8 8" : "M22 200 l3.5 3.5 l6.5 -7"}
            stroke={isClone ? "#991b1b" : "#065f46"}
            strokeWidth="2.2"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <text
            x="35"
            y="204"
            fill={isClone ? "#991b1b" : "#065f46"}
            fontSize="10"
            fontWeight="800"
            fontFamily="sans-serif"
          >
            {isClone ? "CLONE DETECTED" : "CHECKS PASSED"}
          </text>
        </g>
        {/* Sweeping laser line */}
        <rect x="42" y="166" width="276" height="4" rx="2" fill="url(#laserGlow)" />
        {/* Corner reticle brackets */}
        <g stroke={isClone ? "#f87171" : "#2dd4bf"} strokeWidth="2.5" fill="none">
          <path d="M58 42 H42 V58" />
          <path d="M302 42 H318 V58" />
          <path d="M58 262 H42 V246" />
          <path d="M302 262 H318 V246" />
        </g>
      </svg>
    </div>
  );
}

export default function MedicineScene({ embedded = false }: { embedded?: boolean }) {
  const { t } = useI18n();
  const host = useRef<HTMLDivElement>(null);
  const badgeTextRef = useRef<HTMLSpanElement>(null);
  const badgeDotRef = useRef<HTMLSpanElement>(null);
  const badgeWrapRef = useRef<HTMLDivElement>(null);
  const [fallback, setFallback] = useState(false);

  const genuineText = t("heroStateGenuine");
  const cloneText = t("heroStateClone");
  const textsRef = useRef({ genuineText, cloneText });
  textsRef.current = { genuineText, cloneText };

  useEffect(() => {
    const el = host.current;
    if (!el) return;

    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const cores = navigator.hardwareConcurrency ?? 8;
    const mem = (navigator as { deviceMemory?: number }).deviceMemory ?? 8;
    if (reducedMotion || (embedded && (cores <= 4 || mem <= 2))) {
      setFallback(true);
      return;
    }

    let isSoftwareGl = false;
    try {
      const probe = document.createElement("canvas").getContext("webgl2");
      if (!probe) {
        const probe1 = document.createElement("canvas").getContext("webgl");
        if (!probe1) {
          setFallback(true);
          return;
        }
      } else {
        const ext = probe.getExtension("WEBGL_debug_renderer_info");
        const param = ext ? ext.UNMASKED_RENDERER_WEBGL : probe.RENDERER;
        const gpu = String(probe.getParameter(param));
        probe.getExtension("WEBGL_lose_context")?.loseContext();
        isSoftwareGl = /SwiftShader|llvmpipe|softpipe|Software|Basic Render/i.test(gpu);
      }
    } catch {
      setFallback(true);
      return;
    }

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        antialias: !isSoftwareGl,
        alpha: true,
        powerPreference: "high-performance",
      });
    } catch {
      setFallback(true);
      return;
    }

    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;
    renderer.setPixelRatio(isSoftwareGl ? 1 : Math.min(window.devicePixelRatio || 1, 1.75));
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100);
    camera.position.set(0, 0.15, 5.4);
    camera.lookAt(0, 0, 0);

    // Procedural Textures for Genuine & Clone States
    const frontGenuineTex = drawFrontTexture("genuine");
    const frontCloneTex = drawFrontTexture("clone");
    const sideTex = drawSideTexture();
    const maxAniso = renderer.capabilities.getMaxAnisotropy?.() ?? 1;
    frontGenuineTex.anisotropy = maxAniso;
    frontCloneTex.anisotropy = maxAniso;
    sideTex.anisotropy = maxAniso;

    // Composite 10-part Medicine Pack Group
    const packGroup = new THREE.Group();
    scene.add(packGroup);

    // 1. Primary pharmaceutical carton body (6 materials)
    const boxGeo = new THREE.BoxGeometry(1.78, 2.38, 0.72);
    const sideMat = new THREE.MeshStandardMaterial({
      map: sideTex,
      roughness: 0.55,
      metalness: 0.05,
    });
    const capMat = new THREE.MeshStandardMaterial({
      color: 0x0b4f4a,
      roughness: 0.4,
      metalness: 0.15,
    });
    const frontMat = new THREE.MeshStandardMaterial({
      map: frontGenuineTex,
      roughness: 0.35,
      metalness: 0.08,
    });
    const backMat = new THREE.MeshStandardMaterial({
      map: sideTex,
      roughness: 0.6,
      metalness: 0.05,
    });
    const boxMaterials = [sideMat, sideMat, capMat, capMat, frontMat, backMat];
    const cartonMesh = new THREE.Mesh(boxGeo, boxMaterials);
    packGroup.add(cartonMesh);

    // 2. Top tamper-evident holographic seal strip
    const sealGeo = new THREE.BoxGeometry(0.66, 0.04, 0.44);
    const sealMat = new THREE.MeshStandardMaterial({
      color: 0x5eead4,
      roughness: 0.2,
      metalness: 0.75,
      emissive: 0x0f766e,
      emissiveIntensity: 0.25,
    });
    const sealMesh = new THREE.Mesh(sealGeo, sealMat);
    sealMesh.position.set(0, 1.2, 0);
    packGroup.add(sealMesh);

    // 3. Raised DataMatrix hollow frame ring on front face (keeps 14x14 DataMatrix 100% visible)
    const bezelGeo = new THREE.RingGeometry(0.58, 0.62, 4);
    bezelGeo.rotateZ(Math.PI / 4);
    const bezelMat = new THREE.MeshStandardMaterial({
      color: 0x14b8a6,
      roughness: 0.25,
      metalness: 0.5,
      emissive: 0x0d9488,
      emissiveIntensity: 0.35,
    });
    const bezelMesh = new THREE.Mesh(bezelGeo, bezelMat);
    bezelMesh.position.set(-0.33, -0.14, 0.365);
    packGroup.add(bezelMesh);

    // 4-7. Four 3D Scanner Reticle Corner Brackets floating in front of carton
    const reticleGroup = new THREE.Group();
    const bracketGeo = new THREE.BoxGeometry(0.28, 0.045, 0.045);
    const bracketMat = new THREE.MeshStandardMaterial({
      color: 0x2dd4bf,
      roughness: 0.2,
      metalness: 0.6,
      emissive: 0x14b8a6,
      emissiveIntensity: 0.65,
    });
    const corners: [number, number, number][] = [
      [-1.08, 1.32, 0.48],
      [1.08, 1.32, 0.48],
      [-1.08, -1.32, 0.48],
      [1.08, -1.32, 0.48],
    ];
    for (const [cx, cy, cz] of corners) {
      const hBar = new THREE.Mesh(bracketGeo, bracketMat);
      hBar.position.set(cx + (cx < 0 ? 0.11 : -0.11), cy, cz);
      const vBar = new THREE.Mesh(bracketGeo, bracketMat);
      vBar.rotation.z = Math.PI / 2;
      vBar.position.set(cx, cy + (cy < 0 ? 0.11 : -0.11), cz);
      reticleGroup.add(hBar, vBar);
    }
    packGroup.add(reticleGroup);

    // 8. Sweeping Laser Scan Line + Curtain
    const laserGroup = new THREE.Group();
    const laserBarGeo = new THREE.PlaneGeometry(2.15, 0.045);
    const laserBarMat = new THREE.MeshBasicMaterial({
      color: 0x2dd4bf,
      transparent: true,
      opacity: 0.95,
      side: THREE.DoubleSide,
    });
    const laserBar = new THREE.Mesh(laserBarGeo, laserBarMat);
    const laserGlowGeo = new THREE.PlaneGeometry(2.1, 0.28);
    const laserGlowMat = new THREE.MeshBasicMaterial({
      color: 0x14b8a6,
      transparent: true,
      opacity: 0.22,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const laserGlow = new THREE.Mesh(laserGlowGeo, laserGlowMat);
    laserGroup.add(laserBar, laserGlow);
    laserGroup.position.set(0, 0, 0.46);
    packGroup.add(laserGroup);

    // 9. Orbital Security Ring around the Medicine Box
    const ringGeo = new THREE.TorusGeometry(1.62, 0.018, 12, 64);
    const ringMat = new THREE.MeshStandardMaterial({
      color: 0x14b8a6,
      roughness: 0.3,
      metalness: 0.5,
      emissive: 0x0d9488,
      emissiveIntensity: 0.4,
    });
    const ringMesh = new THREE.Mesh(ringGeo, ringMat);
    ringMesh.rotation.x = Math.PI / 2.35;
    ringMesh.rotation.y = 0.22;
    scene.add(ringMesh);

    // 10. Grounding Radial Contact Shadow Disc
    const shadowGeo = new THREE.CircleGeometry(1.45, 32);
    const shadowMat = new THREE.MeshBasicMaterial({
      color: 0x041210,
      transparent: true,
      opacity: 0.32,
      depthWrite: false,
    });
    const shadowMesh = new THREE.Mesh(shadowGeo, shadowMat);
    shadowMesh.rotation.x = -Math.PI / 2;
    shadowMesh.position.set(0, -1.55, 0);
    scene.add(shadowMesh);

    // Studio Warm/Cool Lighting Rig
    const hemiLight = new THREE.HemisphereLight(0xe6f7f2, 0x102824, 2.2);
    scene.add(hemiLight);

    const keyLight = new THREE.DirectionalLight(0xfffbeb, 2.8);
    keyLight.position.set(3.2, 4.2, 4.5);
    scene.add(keyLight);

    const rimLight = new THREE.PointLight(0x14b8a6, 3.5, 10);
    rimLight.position.set(-2.5, 1.2, 2.6);
    scene.add(rimLight);

    // Initial pose
    packGroup.rotation.y = -0.32;
    packGroup.rotation.x = 0.08;

    let currentMode: "genuine" | "clone" = "genuine";
    const applyState = (mode: "genuine" | "clone") => {
      if (mode === currentMode) return;
      currentMode = mode;
      const isClone = mode === "clone";
      frontMat.map = isClone ? frontCloneTex : frontGenuineTex;
      frontMat.needsUpdate = true;
      capMat.color.setHex(isClone ? 0x8c1d24 : 0x0b4f4a);
      sealMat.color.setHex(isClone ? 0xfca5a5 : 0x5eead4);
      sealMat.emissive.setHex(isClone ? 0xb91c1c : 0x0f766e);
      bezelMat.color.setHex(isClone ? 0xef4444 : 0x14b8a6);
      bezelMat.emissive.setHex(isClone ? 0xdc2626 : 0x0d9488);
      bracketMat.color.setHex(isClone ? 0xf87171 : 0x2dd4bf);
      bracketMat.emissive.setHex(isClone ? 0xdc2626 : 0x14b8a6);
      laserBarMat.color.setHex(isClone ? 0xf87171 : 0x2dd4bf);
      laserGlowMat.color.setHex(isClone ? 0xef4444 : 0x14b8a6);
      ringMat.color.setHex(isClone ? 0xef4444 : 0x14b8a6);
      ringMat.emissive.setHex(isClone ? 0xb91c1c : 0x0d9488);
      rimLight.color.setHex(isClone ? 0xef4444 : 0x14b8a6);

      if (badgeTextRef.current) {
        badgeTextRef.current.textContent = isClone
          ? textsRef.current.cloneText
          : textsRef.current.genuineText;
      }
      if (badgeWrapRef.current) {
        badgeWrapRef.current.dataset.state = mode;
      }
    };

    const resize = () => {
      const w = Math.max(200, el.clientWidth || 280);
      const h = embedded ? Math.min(340, Math.max(230, Math.round(w * 0.68))) : 280;
      renderer.setSize(w, h, false);
      renderer.domElement.style.width = "100%";
      renderer.domElement.style.height = `${h}px`;
      renderer.domElement.style.display = "block";
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.render(scene, camera);
    };
    resize();

    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(el);
    window.addEventListener("resize", resize);

    let inView = true;
    let tabHidden = document.hidden;
    let disposed = false;
    let frameId = 0;
    let timerId = 0;
    let lastRenderTime = 0;
    const startTime = performance.now();

    function afterDraw(cb: () => void) {
      const gl = renderer.getContext() as WebGL2RenderingContext;
      if (gl && typeof gl.fenceSync === "function") {
        const sync = gl.fenceSync(gl.SYNC_GPU_COMMANDS_COMPLETE, 0);
        gl.flush();
        const poll = () => {
          if (disposed) return;
          const state = sync && gl.getSyncParameter(sync, gl.SYNC_STATUS);
          if (state === gl.UNSIGNALED) {
            timerId = window.setTimeout(poll, 8);
          } else {
            if (sync) gl.deleteSync(sync);
            timerId = window.setTimeout(cb, 90);
          }
        };
        timerId = window.setTimeout(poll, 8);
      } else {
        timerId = window.setTimeout(cb, 90);
      }
    }

    const scheduleNext = () => {
      if (disposed || !inView || tabHidden) return;
      if (isSoftwareGl) {
        afterDraw(tick);
      } else {
        frameId = requestAnimationFrame(tick);
      }
    };

    function tick(now = performance.now()) {
      if (disposed || !inView || tabHidden) return;
      if (!isSoftwareGl && now - lastRenderTime < 33.3) {
        frameId = requestAnimationFrame(tick);
        return;
      }
      lastRenderTime = now;
      const elapsed = (now - startTime) * 0.001;

      // Flip between "genuine" (0..4.2s) and "clone" (4.2..8.4s)
      const cycle = elapsed % 8.4;
      const nextMode = cycle < 4.2 ? "genuine" : "clone";
      applyState(nextMode);

      // Slow calm rotation + flip inflection when mode switches
      const targetRotY = Math.sin(elapsed * 0.65) * 0.44 + (nextMode === "clone" ? 0.14 : -0.14);
      packGroup.rotation.y += (targetRotY - packGroup.rotation.y) * 0.12;
      packGroup.rotation.x = 0.07 + Math.cos(elapsed * 0.8) * 0.04;
      packGroup.position.y = Math.sin(elapsed * 1.4) * 0.05;

      // Laser line sweeps across the GS1 DataMatrix on the front face
      const sweep = Math.sin(elapsed * 2.6);
      laserGroup.position.y = sweep * 0.98;
      ringMesh.rotation.z = elapsed * 0.25;

      if (nextMode === "clone") {
        const pulse = 0.5 + 0.5 * Math.sin(elapsed * 7.0);
        ringMat.emissiveIntensity = 0.35 + pulse * 0.55;
      } else {
        ringMat.emissiveIntensity = 0.35;
      }

      renderer.render(scene, camera);
      scheduleNext();
    }

    let io: IntersectionObserver | undefined;
    if (typeof IntersectionObserver !== "undefined") {
      io = new IntersectionObserver(
        (entries) => {
          const entry = entries[0];
          const wasInView = inView;
          inView = !!entry?.isIntersecting;
          if (inView && !wasInView && !tabHidden) {
            scheduleNext();
          }
        },
        { threshold: 0.05 },
      );
      io.observe(el);
    }

    const onVisibility = () => {
      tabHidden = document.hidden;
      if (!tabHidden && inView) {
        scheduleNext();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    // Draw initial frame immediately and start loop
    renderer.render(scene, camera);
    scheduleNext();

    return () => {
      disposed = true;
      cancelAnimationFrame(frameId);
      clearTimeout(timerId);
      resizeObserver.disconnect();
      window.removeEventListener("resize", resize);
      io?.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      boxGeo.dispose();
      sealGeo.dispose();
      bezelGeo.dispose();
      bracketGeo.dispose();
      laserBarGeo.dispose();
      laserGlowGeo.dispose();
      ringGeo.dispose();
      shadowGeo.dispose();
      frontGenuineTex.dispose();
      frontCloneTex.dispose();
      sideTex.dispose();
      sideMat.dispose();
      capMat.dispose();
      frontMat.dispose();
      backMat.dispose();
      sealMat.dispose();
      bezelMat.dispose();
      bracketMat.dispose();
      laserBarMat.dispose();
      laserGlowMat.dispose();
      ringMat.dispose();
      shadowMat.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [embedded]);

  const content = (
    <div className="hero-scanner-stage">
      <div className="hero-scanner-hud">
        <span className="scanner-hud-label">{t("heroScannerBadge")}</span>
        <div
          ref={badgeWrapRef}
          className="scanner-state-pill"
          data-state="genuine"
          aria-hidden="true"
        >
          <span ref={badgeDotRef} className="scanner-state-dot" />
          <span ref={badgeTextRef}>{t("heroStateGenuine")}</span>
        </div>
      </div>
      {fallback ? (
        <StaticPackSvg />
      ) : (
        <div ref={host} className="medicine-scene" data-testid="three-scene" aria-hidden="true" />
      )}
    </div>
  );

  if (embedded) return content;

  return (
    <section className="card three-card">
      <div className="three-card-header">
        <h2>{t("threeTitle")}</h2>
        <p className="muted">{t("threeHint")}</p>
      </div>
      {content}
    </section>
  );
}
