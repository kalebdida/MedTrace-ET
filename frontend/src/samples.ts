export const GS = "\u001d";
export const DEMO_GTIN = "09506000134352";

/** A fresh serial per demo run, so earlier demo scans don't affect the result. */
export function freshSerial(): string {
  return "DEMO" + Math.random().toString(36).slice(2, 8).toUpperCase();
}

export function pharmaBarcode(serial: string, expiry = "301231", batch = "BATCH42"): string {
  return `]d201${DEMO_GTIN}17${expiry}10${batch}${GS}21${serial}`;
}

export const SAMPLES = [
  { label: "Genuine pack", barcode: () => pharmaBarcode("DEMO0001") },
  { label: "Expired pack", barcode: () => pharmaBarcode("DEMO0002", "240131") },
  { label: "Bad check digit", barcode: () => `]d201095060001343531728123110BATCH42${GS}21DEMO0003` },
];

/** Shows invisible GS separators so users can see the barcode structure. */
export function visible(barcode: string): string {
  return barcode.split(GS).join("⟨GS⟩");
}

export function fromVisible(text: string): string {
  return text.split("⟨GS⟩").join(GS);
}
