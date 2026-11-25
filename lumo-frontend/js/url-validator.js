/**
 * LUMO Safe URL Validator & SSRF Guard (Client-Side Pre-Validation)
 * Enforces scheme allowlists, blocks loopback / private / link-local hosts,
 * detects punycode & suspicious syntax, and NEVER fabricates remote scan results.
 */

const DOWNLOAD_EXTENSIONS = new Set([
  'exe', 'msi', 'dmg', 'pkg', 'deb', 'rpm', 'apk', 'zip', 'tar', 'gz', '7z',
  'rar', 'iso', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'sh',
  'bat', 'ps1', 'jar', 'bin',
]);

/**
 * Checks whether an IPv4 literal falls in loopback, RFC 1918 private,
 * link-local / cloud metadata, or unspecified address ranges.
 *
 * @param {string} host
 * @returns {boolean}
 */
export function isPrivateOrLoopbackIPv4(host) {
  const match = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(host);
  if (!match) return false;

  const octets = match.slice(1).map(Number);
  if (octets.some((n) => n < 0 || n > 255)) return true;

  const [a, b] = octets;
  if (a === 0) return true; // 0.0.0.0/8
  if (a === 10) return true; // 10.0.0.0/8 (RFC 1918)
  if (a === 127) return true; // 127.0.0.0/8 (loopback)
  if (a === 169 && b === 254) return true; // 169.254.0.0/16 (link-local / metadata)
  if (a === 172 && b >= 16 && b <= 31) return true; // 172.16.0.0/12 (RFC 1918)
  if (a === 192 && b === 168) return true; // 192.168.0.0/16 (RFC 1918)
  if (a === 100 && b >= 64 && b <= 127) return true; // 100.64.0.0/10 (CGNAT)
  return false;
}

/**
 * Checks whether a hostname targets internal, loopback, or local infrastructure.
 *
 * @param {string} hostname
 * @returns {boolean}
 */
export function isRestrictedHost(hostname) {
  const clean = String(hostname || '').toLowerCase().replace(/^\[|\]$/g, '');
  if (!clean) return true;

  if (
    clean === 'localhost' ||
    clean.endsWith('.localhost') ||
    clean.endsWith('.local') ||
    clean.endsWith('.internal') ||
    clean.endsWith('.lan') ||
    clean === 'metadata.google.internal'
  ) {
    return true;
  }

  // IPv6 loopback, unspecified, unique-local (fc00::/7), link-local (fe80::/10)
  if (clean.includes(':')) {
    if (
      clean === '::1' ||
      clean === '::' ||
      clean.startsWith('fc') ||
      clean.startsWith('fd') ||
      clean.startsWith('fe8') ||
      clean.startsWith('fe9') ||
      clean.startsWith('fea') ||
      clean.startsWith('feb') ||
      clean.startsWith('::ffff:127.') ||
      clean.startsWith('::ffff:10.') ||
      clean.startsWith('::ffff:192.168.')
    ) {
      return true;
    }
  }

  return isPrivateOrLoopbackIPv4(clean);
}

/**
 * Validates and structurally inspects a submitted URL locally.
 * Always reports remote security classification as 'Unknown' when no backend is active.
 *
 * @param {string} rawInput
 */
export function validateAndInspectUrl(rawInput) {
  const input = String(rawInput || '').trim();
  if (!input) {
    return {
      ok: false,
      blocked: false,
      error: 'Enter a full HTTP or HTTPS URL to inspect.',
    };
  }

  let parsed;
  try {
    parsed = new URL(input);
  } catch {
    return {
      ok: false,
      blocked: false,
      error: 'Invalid URL format. Include the scheme, for example https://example.org/file.pdf.',
    };
  }

  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    return {
      ok: false,
      blocked: true,
      error: `Blocked unsupported scheme "${parsed.protocol}". Only public HTTP and HTTPS URLs are permitted.`,
    };
  }

  if (isRestrictedHost(parsed.hostname)) {
    return {
      ok: false,
      blocked: true,
      error:
        'Blocked by SSRF protection: private networks, loopback addresses, and internal hostnames cannot be scanned.',
    };
  }

  const pathSegments = parsed.pathname.split('/').filter(Boolean);
  const lastSegment = pathSegments.length > 0 ? pathSegments[pathSegments.length - 1] : '';
  const extMatch = /\.([a-z0-9]{1,8})$/i.exec(lastSegment);
  const fileExtension = extMatch ? extMatch[1].toLowerCase() : null;
  const isDownloadCandidate = Boolean(fileExtension && DOWNLOAD_EXTENSIONS.has(fileExtension));
  const hasPunycode = parsed.hostname.toLowerCase().includes('xn--');
  const hasUserInfo = Boolean(parsed.username || parsed.password);
  const usesPlainHttp = parsed.protocol === 'http:';
  const isRawIp = /^\d{1,3}(\.\d{1,3}){3}$/.test(parsed.hostname);

  const syntacticNotes = [];
  if (usesPlainHttp) {
    syntacticNotes.push('Uses unencrypted HTTP instead of HTTPS.');
  }
  if (hasPunycode) {
    syntacticNotes.push('Contains internationalized Punycode (xn--) domain label — verify for homograph lookalikes.');
  }
  if (hasUserInfo) {
    syntacticNotes.push('Contains embedded userinfo (@) credentials in URL, a common URL obfuscation pattern.');
  }
  if (isRawIp) {
    syntacticNotes.push('Targets a raw IP address instead of a registered domain name.');
  }
  if (isDownloadCandidate) {
    syntacticNotes.push(`Path ends with .${fileExtension}, indicating a likely downloadable file.`);
  }

  return {
    ok: true,
    blocked: false,
    normalizedUrl: parsed.href,
    protocol: parsed.protocol,
    hostname: parsed.hostname,
    port: parsed.port || (parsed.protocol === 'https:' ? '443' : '80'),
    pathname: parsed.pathname || '/',
    queryParamCount: [...parsed.searchParams.keys()].length,
    fileExtension,
    isDownloadCandidate,
    hasPunycode,
    hasUserInfo,
    usesPlainHttp,
    syntacticNotes,
    // Strictly honest: never fabricate a clean or malicious verdict without backend threat intelligence.
    riskClassification: 'Unknown',
    backendRequired: true,
  };
}
