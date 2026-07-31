const HTTP_PROTOCOLS = new Set(["http:", "https:"]);

export const redirectAliasToCanonicalOrigin = (
  request: Request,
  appOrigin?: string,
): Response | null => {
  if (!appOrigin) {
    return null;
  }

  let canonical: URL;
  try {
    canonical = new URL(appOrigin);
  } catch {
    return null;
  }
  if (
    !HTTP_PROTOCOLS.has(canonical.protocol) ||
    canonical.pathname !== "/" ||
    canonical.search ||
    canonical.hash
  ) {
    return null;
  }

  const requested = new URL(request.url);
  if (requested.hostname !== `www.${canonical.hostname}`) {
    return null;
  }

  const destination = new URL(canonical.origin);
  destination.pathname = requested.pathname;
  destination.search = requested.search;
  return new Response(null, {
    status: 308,
    headers: {
      location: destination.toString(),
      "cache-control": "public, max-age=3600",
    },
  });
};
