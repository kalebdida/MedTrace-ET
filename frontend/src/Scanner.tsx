import { useEffect, useRef, useState } from "react";
import { BrowserMultiFormatReader } from "@zxing/browser";
import { BarcodeFormat, DecodeHintType } from "@zxing/library";

/** Live camera DataMatrix scanner. ZXing emits GS1 FNC1 separators as ASCII 29, which the backend needs. */
export function Scanner({ onScan, onClose }: { onScan: (text: string) => void; onClose: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const hints = new Map();
    hints.set(DecodeHintType.POSSIBLE_FORMATS, [BarcodeFormat.DATA_MATRIX, BarcodeFormat.QR_CODE]);
    hints.set(DecodeHintType.TRY_HARDER, true);
    const reader = new BrowserMultiFormatReader(hints);
    let stop: (() => void) | undefined;
    reader
      .decodeFromConstraints({ video: { facingMode: "environment" } }, video.current!, (result, _err, controls) => {
        if (result) {
          controls.stop();
          const format = result.getBarcodeFormat();
          const text = result.getText();
          // GS1 DataMatrix: add the symbology prefix so the backend knows it is GS1.
          onScan(format === BarcodeFormat.DATA_MATRIX && !text.startsWith("]") ? "]d2" + text : text);
        }
      })
      .then((controls) => (stop = () => controls.stop()))
      .catch(() => setError("Camera unavailable. Allow camera access, or type the barcode instead."));
    return () => stop?.();
  }, [onScan]);

  return (
    <div className="scanner">
      {error ? <p className="error">{error}</p> : <video ref={video} muted playsInline />}
      <p className="hint">Point the camera at the DataMatrix code on the pack.</p>
      <button className="secondary" onClick={onClose}>Cancel</button>
    </div>
  );
}
