const KNOWN_CREATOR_ORIGINS: Readonly<Record<string, string>> = {
  "https://admin.qiko.ai": "https://qiko.ai",
  "https://admin.preprod.qiko.ai": "https://preprod.qiko.ai",
};

function configuredCreatorOrigin(value: string): string {
  let url: URL;

  try {
    url = new URL(value.trim());
  } catch {
    throw new Error("Configured creator URL must be a valid HTTP(S) origin.");
  }

  const hasQueryOrHash = url.href.includes("?") || url.href.includes("#");
  if (
    (url.protocol !== "http:" && url.protocol !== "https:")
    || url.username !== ""
    || url.password !== ""
    || url.pathname !== "/"
    || hasQueryOrHash
  ) {
    throw new Error("Configured creator URL must be a credential-free HTTP(S) origin.");
  }

  return url.origin;
}

export function resolveCreatorOrigin(
  adminOrigin: string,
  configuredOrigin?: string,
): string {
  if (configuredOrigin?.trim()) {
    return configuredCreatorOrigin(configuredOrigin);
  }

  const creatorOrigin = KNOWN_CREATOR_ORIGINS[adminOrigin];
  if (creatorOrigin) return creatorOrigin;

  throw new Error("Creator origin must be configured for this admin origin.");
}
