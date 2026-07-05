"use client";
// V2 stores integration tokens server-side; the client never decrypts them. Stub returns "".
export async function resolveDecryptedCalendlyToken(_raw: string): Promise<string> {
  return "";
}
