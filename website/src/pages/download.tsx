import React, { useEffect, useMemo, useState } from 'react';
import Layout from '@theme/Layout';

/**
 * The download page.
 *
 * This page used to link to relative paths like `/api/download/windows` with a
 * `download="TchueKAM-Setup.exe"` attribute. On a static host nothing answers
 * those paths, so the browser saved the 404 page itself under the installer's
 * name — and Windows reported "This app can't run on your PC" for what was
 * really a few dozen bytes of HTML.
 *
 * Two rules keep that from happening again:
 *
 *   1. Only ever link to the absolute URL of a published release asset. There
 *      is then no same-origin path that can turn an error page into a download.
 *   2. Only render a platform that actually has an asset in the release. A
 *      button that cannot deliver an installer is never drawn.
 *
 * Release data comes from `/api/download-info` when a backend is present, and
 * otherwise straight from the public GitHub releases API, so the page shows the
 * real version and file sizes on a purely static deployment too.
 */

const RELEASES_API = 'https://api.github.com/repos/Tchuekam/tchuekam-desktop/releases/latest';
const RELEASES_PAGE = 'https://github.com/Tchuekam/tchuekam-desktop/releases/latest';

const ACCENT = '#00E5FF';

type PlatformId = 'windows' | 'mac-arm64' | 'mac-x64' | 'linux' | 'android';

interface PlatformSpec {
  id: PlatformId;
  label: string;
  icon: string;
  fileType: string;
  /** Asset name produced by electron-builder; this is what we look for. */
  filename: string;
  /** Matched against the user agent to pick the default download. */
  matches: (ua: string) => boolean;
}

interface ReleaseAsset {
  url: string;
  size: number;
  sha256?: string | null;
}

interface ReleaseState {
  version: string | null;
  assets: Partial<Record<PlatformId, ReleaseAsset>>;
  status: 'loading' | 'ready' | 'unavailable';
}

/** Table-driven: adding a platform here is the only change a new target needs. */
const PLATFORMS: PlatformSpec[] = [
  {
    id: 'windows',
    label: 'Windows (64-bit)',
    icon: '🪟',
    fileType: '.exe installer',
    filename: 'TchueKAM-Setup.exe',
    matches: (ua) => ua.includes('windows') || ua.includes('win64'),
  },
  {
    id: 'mac-arm64',
    label: 'macOS (Apple Silicon)',
    icon: '🍏',
    fileType: '.dmg',
    filename: 'TchueKAM-Mac-arm64.dmg',
    matches: (ua) => ua.includes('mac os') || ua.includes('macintosh'),
  },
  {
    id: 'mac-x64',
    label: 'macOS (Intel)',
    icon: '🍏',
    fileType: '.dmg',
    filename: 'TchueKAM-Mac-x64.dmg',
    matches: () => false,
  },
  {
    id: 'linux',
    label: 'Linux',
    icon: '🐧',
    fileType: '.AppImage',
    filename: 'TchueKAM-Linux.AppImage',
    matches: (ua) => ua.includes('linux') || ua.includes('x11'),
  },
  {
    id: 'android',
    label: 'Android (64-bit)',
    icon: '🤖',
    fileType: '.apk package',
    filename: 'TchueKAM-Mobile.apk',
    matches: (ua) => ua.includes('android'),
  },
];

/** An asset far below this is a placeholder or a truncated upload, not an installer. */
const MIN_INSTALLER_BYTES = 1_000_000;

function formatSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '';
  const mb = bytes / (1024 * 1024);
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb.toFixed(1)} MB`;
}

function detectPlatform(ua: string): PlatformId | null {
  // Android first: its user agent also contains "Linux".
  const android = PLATFORMS.find((p) => p.id === 'android');
  if (android && android.matches(ua)) return 'android';
  const match = PLATFORMS.find((p) => p.id !== 'android' && p.matches(ua));
  return match ? match.id : null;
}

interface GithubAsset {
  name?: string;
  size?: number;
  digest?: string | null;
  browser_download_url?: string;
}

function readGithubRelease(payload: {
  tag_name?: string;
  assets?: GithubAsset[];
}): ReleaseState {
  const assets: Partial<Record<PlatformId, ReleaseAsset>> = {};
  for (const spec of PLATFORMS) {
    const found = (payload.assets ?? []).find((a) => a.name === spec.filename);
    // Size is the cheap, decisive guard: it is what separates the real
    // 114 MB installer from the 66-byte file that caused the outage.
    if (!found?.browser_download_url || (found.size ?? 0) < MIN_INSTALLER_BYTES) continue;
    assets[spec.id] = {
      url: found.browser_download_url,
      size: found.size ?? 0,
      sha256: found.digest?.startsWith('sha256:') ? found.digest.slice('sha256:'.length) : null,
    };
  }
  return {
    version: (payload.tag_name ?? '').replace(/^v/, '') || null,
    assets,
    status: 'ready',
  };
}

interface DownloadInfoPayload {
  version?: string | null;
  platforms?: Record<string, { url?: string; size?: number; sha256?: string | null }>;
}

function readDownloadInfo(payload: DownloadInfoPayload): ReleaseState | null {
  const platforms = payload.platforms ?? {};
  const assets: Partial<Record<PlatformId, ReleaseAsset>> = {};
  for (const spec of PLATFORMS) {
    const entry = platforms[spec.id];
    if (!entry?.url || (entry.size ?? 0) < MIN_INSTALLER_BYTES) continue;
    assets[spec.id] = { url: entry.url, size: entry.size ?? 0, sha256: entry.sha256 ?? null };
  }
  if (Object.keys(assets).length === 0) return null;
  return { version: payload.version ?? null, assets, status: 'ready' };
}

function useRelease(): ReleaseState {
  const [state, setState] = useState<ReleaseState>({
    version: null,
    assets: {},
    status: 'loading',
  });

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      // A deployment with the Tchuekam backend answers this with manifest data
      // that the release pipeline already verified.
      try {
        const res = await fetch('/api/download-info', { headers: { Accept: 'application/json' } });
        if (res.ok) {
          const parsed = readDownloadInfo(await res.json());
          if (parsed && !cancelled) {
            setState(parsed);
            return;
          }
        }
      } catch {
        // Static hosting has no backend; fall through to the public release API.
      }

      try {
        const res = await fetch(RELEASES_API, { headers: { Accept: 'application/vnd.github+json' } });
        if (!res.ok) throw new Error(`releases API returned ${res.status}`);
        if (!cancelled) setState(readGithubRelease(await res.json()));
      } catch {
        if (!cancelled) setState({ version: null, assets: {}, status: 'unavailable' });
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}

const cardStyle: React.CSSProperties = {
  width: '100%',
  maxWidth: '720px',
  backgroundColor: 'rgba(255, 255, 255, 0.03)',
  backdropFilter: 'blur(16px)',
  border: '1px solid rgba(255, 255, 255, 0.1)',
  borderRadius: '16px',
  padding: '2.5rem 2rem',
  boxShadow: '0 20px 40px rgba(0, 0, 0, 0.3)',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
};

function PrimaryDownload({ spec, asset }: { spec: PlatformSpec; asset: ReleaseAsset }) {
  return (
    <a
      href={asset.url}
      style={{
        flex: '1 1 240px',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '0.6rem',
        padding: '0.9rem 1.5rem',
        borderRadius: '12px',
        backgroundColor: ACCENT,
        color: '#07070d',
        fontWeight: 700,
        fontSize: '1.05rem',
        textDecoration: 'none',
        boxShadow: '0 8px 24px rgba(0, 229, 255, 0.25)',
      }}
    >
      <span style={{ fontSize: '1.2rem', lineHeight: 1 }}>↓</span>
      Download for {spec.label}
      {asset.size > 0 && (
        <span style={{ fontWeight: 600, opacity: 0.75 }}>({formatSize(asset.size)})</span>
      )}
    </a>
  );
}

export default function DownloadPage(): React.JSX.Element {
  const release = useRelease();
  const [detected, setDetected] = useState<PlatformId | null>(null);

  useEffect(() => {
    setDetected(detectPlatform(navigator.userAgent.toLowerCase()));
  }, []);

  // Offer the visitor's own platform first, but only when it really exists in
  // this release; otherwise fall back to whatever did ship. We track which of
  // the two happened, because telling a Mac user "we detected Windows" is the
  // kind of confident-sounding nonsense this page is meant to stop producing.
  const primary = useMemo(() => {
    const order: (PlatformId | null)[] = [detected, 'windows', 'mac-arm64', 'linux'];
    for (const id of order) {
      if (id && release.assets[id]) {
        const spec = PLATFORMS.find((p) => p.id === id);
        if (spec) {
          return { spec, asset: release.assets[id] as ReleaseAsset, isForDetected: id === detected };
        }
      }
    }
    return null;
  }, [detected, release.assets]);

  const detectedSpec = PLATFORMS.find((p) => p.id === detected);

  const available = PLATFORMS.filter((p) => release.assets[p.id]);
  const unavailable = PLATFORMS.filter((p) => !release.assets[p.id]);

  return (
    <Layout
      title="Download TchueKAM Agent"
      description="Download TchueKAM Agent for Windows, macOS, and Linux — fast, private, native AI."
    >
      <main
        style={{
          minHeight: '80vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '3rem 1rem',
          background: 'radial-gradient(circle at 50% 20%, rgba(0, 229, 255, 0.08), transparent 70%)',
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: '2.5rem' }}>
          <h1 style={{ fontSize: '2.5rem', fontWeight: 800, marginBottom: '0.75rem', letterSpacing: '-0.02em' }}>
            TchueKAM Agent
          </h1>
          <p
            style={{
              fontSize: '1.2rem',
              color: 'var(--ifm-color-content-secondary)',
              maxWidth: '600px',
              margin: '0 auto',
            }}
          >
            Your native desktop AI assistant — fast, private, and yours.
          </p>
        </div>

        <div style={cardStyle}>
          {release.version && (
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.35rem 0.85rem',
                borderRadius: '9999px',
                backgroundColor: 'rgba(0, 229, 255, 0.12)',
                color: ACCENT,
                fontSize: '0.85rem',
                fontWeight: 600,
                marginBottom: '1.5rem',
                border: '1px solid rgba(0, 229, 255, 0.3)',
              }}
            >
              <span>v{release.version}</span>
              <span style={{ opacity: 0.7 }}>•</span>
              <span>Latest release</span>
            </div>
          )}

          {release.status === 'loading' && (
            <p style={{ color: 'var(--ifm-color-content-secondary)' }}>Checking the latest release…</p>
          )}

          {release.status === 'unavailable' && (
            <div style={{ textAlign: 'center' }}>
              <p style={{ marginBottom: '0.75rem' }}>
                We could not reach the release service just now, so we are not showing a download
                rather than risk handing you a file that will not install.
              </p>
              <a href={RELEASES_PAGE} style={{ color: ACCENT, fontWeight: 600 }}>
                Browse all releases on GitHub →
              </a>
            </div>
          )}

          {release.status === 'ready' && primary && (
            <>
              <p
                style={{
                  fontSize: '1.05rem',
                  color: 'var(--ifm-color-content-secondary)',
                  marginBottom: '1.5rem',
                  textAlign: 'center',
                }}
              >
                {primary.isForDetected ? (
                  <>
                    We detected <strong>{primary.spec.label}</strong>. Download and run the installer:
                  </>
                ) : detectedSpec ? (
                  <>
                    There is no <strong>{detectedSpec.label}</strong> build in this release yet. What
                    is available today:
                  </>
                ) : (
                  <>Download and run the installer:</>
                )}
              </p>
              <div
                style={{
                  display: 'flex',
                  gap: '1rem',
                  width: '100%',
                  maxWidth: '560px',
                  marginBottom: '2rem',
                  justifyContent: 'center',
                }}
              >
                <PrimaryDownload spec={primary.spec} asset={primary.asset} />
              </div>
            </>
          )}

          {release.status === 'ready' && available.length > 0 && (
            <table
              style={{
                width: '100%',
                borderCollapse: 'collapse',
                textAlign: 'left',
                fontSize: '0.95rem',
                marginBottom: '1.5rem',
              }}
            >
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.1)' }}>
                  <th style={{ padding: '0.75rem 1rem', fontWeight: 600 }}>Platform</th>
                  <th style={{ padding: '0.75rem 1rem', fontWeight: 600 }}>File</th>
                  <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontWeight: 600 }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {available.map((spec) => {
                  const asset = release.assets[spec.id] as ReleaseAsset;
                  return (
                    <tr key={spec.id} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                      <td style={{ padding: '0.9rem 1rem', fontWeight: 600 }}>
                        <span style={{ marginRight: '0.4rem' }}>{spec.icon}</span>
                        {spec.label}
                      </td>
                      <td style={{ padding: '0.9rem 1rem' }}>
                        <code style={{ padding: '0.2rem 0.4rem', borderRadius: '4px' }}>{spec.fileType}</code>
                        {asset.size > 0 && (
                          <span
                            style={{
                              marginLeft: '0.5rem',
                              fontSize: '0.8rem',
                              color: 'var(--ifm-color-content-secondary)',
                            }}
                          >
                            {formatSize(asset.size)}
                          </span>
                        )}
                      </td>
                      <td style={{ padding: '0.9rem 1rem', textAlign: 'right' }}>
                        <a href={asset.url} style={{ color: ACCENT, textDecoration: 'none', fontWeight: 600 }}>
                          Download →
                        </a>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          {release.status === 'ready' && unavailable.length > 0 && (
            <p
              style={{
                fontSize: '0.85rem',
                color: 'var(--ifm-color-content-secondary)',
                margin: '0 0 0.75rem',
                textAlign: 'center',
              }}
            >
              Not in this release yet: {unavailable.map((p) => p.label).join(', ')}. We list a platform
              only once a verified installer exists for it.
            </p>
          )}

          {release.status === 'ready' && (
            <p
              style={{
                fontSize: '0.85rem',
                color: 'var(--ifm-color-content-secondary)',
                margin: 0,
                textAlign: 'center',
                opacity: 0.85,
              }}
            >
              Every installer is checked for a valid executable signature and size before release.{' '}
              <a href={RELEASES_PAGE} style={{ color: ACCENT }}>
                Release history
              </a>
            </p>
          )}
        </div>
      </main>
    </Layout>
  );
}
