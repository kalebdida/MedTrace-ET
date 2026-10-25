import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { useI18n } from "./i18n";
export default function MedicineScene() {
  const { t } = useI18n();
  const host = useRef<HTMLDivElement>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (!host.current) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setError(true);
      return;
    }
    const el = host.current;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
    camera.position.z = 5;
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
    el.appendChild(renderer.domElement);
    const geometry = new THREE.CapsuleGeometry(0.45, 0.8, 8, 24);
    const material = new THREE.MeshStandardMaterial({
      color: 0x24a896,
      roughness: 0.3,
      metalness: 0.1,
    });
    const capsule = new THREE.Mesh(geometry, material);
    capsule.rotation.z = -0.65;
    scene.add(capsule);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x28423f, 3));
    const light = new THREE.DirectionalLight(0xffffff, 4);
    light.position.set(2, 3, 4);
    scene.add(light);
    const bandGeometry = new THREE.TorusGeometry(0.455, 0.025, 8, 40);
    const bandMaterial = new THREE.MeshStandardMaterial({ color: 0xe9f4ef });
    const band = new THREE.Mesh(bandGeometry, bandMaterial);
    band.rotation.x = Math.PI / 2;
    capsule.add(band);
    const draw = () => renderer.render(scene, camera);
    const resize = () => {
      const w = el.clientWidth;
      renderer.setSize(w, 240);
      camera.aspect = w / 240;
      camera.updateProjectionMatrix();
      draw();
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(el);
    const move = (e: PointerEvent) => {
      if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      capsule.rotation.y = (e.offsetX / el.clientWidth - 0.5) * 2;
      draw();
    };
    el.addEventListener("pointermove", move);
    return () => {
      observer.disconnect();
      el.removeEventListener("pointermove", move);
      geometry.dispose();
      material.dispose();
      bandGeometry.dispose();
      bandMaterial.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);
  return (
    <section className="card">
      <h2>{t("threeTitle")}</h2>
      <p>{t("threeHint")}</p>
      {error ? <p>{t("threeError")}</p> : <div ref={host} className="medicine-scene" aria-hidden />}
    </section>
  );
}
