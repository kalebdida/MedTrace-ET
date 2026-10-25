import { useEffect, useRef, useState } from "react";
import { BrowserMultiFormatReader, type IScannerControls } from "@zxing/browser";
import { BarcodeFormat, DecodeHintType } from "@zxing/library";
import { useI18n } from "./i18n";
export function Scanner({
  onScan,
  onClose,
}: {
  onScan: (text: string) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const video = useRef<HTMLVideoElement>(null);
  const controlsRef = useRef<IScannerControls | undefined>(undefined);
  const [error, setError] = useState(false);
  const [torch, setTorch] = useState(false);
  const [supported, setSupported] = useState(false);
  const [torchError, setTorchError] = useState(false);
  useEffect(() => {
    let disposed = false;
    let completed = false;
    const hints = new Map();
    hints.set(DecodeHintType.POSSIBLE_FORMATS, [BarcodeFormat.DATA_MATRIX, BarcodeFormat.QR_CODE]);
    hints.set(DecodeHintType.TRY_HARDER, true);
    const reader = new BrowserMultiFormatReader(hints);
    reader
      .decodeFromConstraints(
        { video: { facingMode: "environment", width: { ideal: 1280 } }, audio: false },
        video.current!,
        (result, _err, controls) => {
          if (disposed || completed || !result) return;
          completed = true;
          controls.stop();
          navigator.vibrate?.(80);
          const text = result.getText();
          onScan(
            result.getBarcodeFormat() === BarcodeFormat.DATA_MATRIX && !text.startsWith("]")
              ? "]d2" + text
              : text,
          );
        },
      )
      .then((controls) => {
        if (disposed) {
          controls.stop();
          return;
        }
        controlsRef.current = controls;
        setSupported(!!controls.switchTorch);
      })
      .catch(() => {
        if (!disposed) setError(true);
      });
    return () => {
      disposed = true;
      controlsRef.current?.stop();
      controlsRef.current = undefined;
    };
  }, [onScan]);
  async function toggle() {
    try {
      await controlsRef.current?.switchTorch?.(!torch);
      setTorch(!torch);
      setTorchError(false);
    } catch {
      setTorchError(true);
    }
  }
  return (
    <section className="scanner">
      {error ? (
        <p className="error" role="alert">
          {t("cameraError")}
        </p>
      ) : (
        <div className="viewfinder">
          <video ref={video} muted playsInline />
          <div className="target-box" aria-hidden="true">
            <span className="vf-corner tl" />
            <span className="vf-corner tr" />
            <span className="vf-corner bl" />
            <span className="vf-corner br" />
            <span className="vf-laser" />
          </div>
        </div>
      )}
      <p>{t("cameraHint")}</p>
      {supported && !error && (
        <button className="secondary" aria-pressed={torch} onClick={toggle}>
          {t(torch ? "torchOff" : "torchOn")}
        </button>
      )}
      {torchError && <p role="alert">{t("torchError")}</p>}
      <button className="secondary" onClick={onClose}>
        {t("cameraClose")}
      </button>
    </section>
  );
}
