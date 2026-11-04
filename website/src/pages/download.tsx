import React from 'react';
import Layout from '@theme/Layout';

export default function DownloadPage(): React.JSX.Element {
  const handleWindowsDownload = (e: React.MouseEvent<HTMLAnchorElement>) => {
    const downloadUrl = '/api/download/windows';
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.setAttribute('download', 'TchueKAM-Setup.exe');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleAndroidDownload = (e: React.MouseEvent<HTMLAnchorElement>) => {
    const downloadUrl = '/api/download/android';
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.setAttribute('download', 'TchueKAM-Mobile.apk');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <Layout
      title="Download TchueKAM Agent"
      description="Download TchueKAM Agent for Windows, macOS, Linux, and Mobile (Android & iOS) — fast, private, native AI."
    >
      <main style={{
        minHeight: '80vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '3rem 1rem',
        background: 'radial-gradient(circle at 50% 20%, rgba(0, 229, 255, 0.08), transparent 70%)',
      }}>
        <div style={{ textAlign: 'center', marginBottom: '2.5rem' }}>
          <h1 style={{ fontSize: '2.5rem', fontWeight: 800, marginBottom: '0.75rem', letterSpacing: '-0.02em' }}>
            TchueKAM Agent
          </h1>
          <p style={{ fontSize: '1.2rem', color: 'var(--ifm-color-content-secondary)', maxWidth: '600px', margin: '0 auto' }}>
            Your native desktop & mobile AI assistant — fast, private, and yours.
          </p>
        </div>

        <div style={{
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
        }}>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.35rem 0.85rem',
            borderRadius: '9999px',
            backgroundColor: 'rgba(0, 229, 255, 0.12)',
            color: '#00E5FF',
            fontSize: '0.85rem',
            fontWeight: 600,
            marginBottom: '1.5rem',
            border: '1px solid rgba(0, 229, 255, 0.3)',
          }}>
            <span style={{ fontSize: '0.8rem' }}>v1.0.0</span>
            <span style={{ opacity: 0.7 }}>•</span>
            <span>Desktop & Mobile Released</span>
          </div>

          <p style={{ fontSize: '1.05rem', color: 'var(--ifm-color-content-secondary)', marginBottom: '1.5rem' }}>
            Download TchueKAM in one click or try it instantly:
          </p>

          {/* Primary Action Buttons */}
          <div style={{
            display: 'flex',
            gap: '1rem',
            width: '100%',
            maxWidth: '560px',
            marginBottom: '2rem',
            flexWrap: 'wrap',
            justifyContent: 'center'
          }}>
            <a
              href="/api/download/windows"
              onClick={handleWindowsDownload}
              download="TchueKAM-Setup.exe"
              style={{
                flex: '1 1 240px',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '0.6rem',
                padding: '0.9rem 1.5rem',
                borderRadius: '12px',
                backgroundColor: '#00E5FF',
                color: '#07070d',
                fontWeight: 700,
                fontSize: '1.05rem',
                textDecoration: 'none',
                boxShadow: '0 8px 24px rgba(0, 229, 255, 0.25)',
                transition: 'transform 0.2s ease, box-shadow 0.2s ease',
                cursor: 'pointer',
              }}
              onMouseOver={(e) => {
                e.currentTarget.style.transform = 'translateY(-2px)';
                e.currentTarget.style.boxShadow = '0 12px 28px rgba(0, 229, 255, 0.4)';
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.transform = 'translateY(0)';
                e.currentTarget.style.boxShadow = '0 8px 24px rgba(0, 229, 255, 0.25)';
              }}
            >
              <span style={{ fontSize: '1.2rem', lineHeight: 1 }}>↓</span>
              Windows (x64)
            </a>

            <a
              href="/api/download/android"
              onClick={handleAndroidDownload}
              download="TchueKAM-Mobile.apk"
              style={{
                flex: '1 1 240px',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '0.6rem',
                padding: '0.9rem 1.5rem',
                borderRadius: '12px',
                backgroundColor: 'rgba(255, 255, 255, 0.08)',
                color: '#fff',
                fontWeight: 700,
                fontSize: '1.05rem',
                textDecoration: 'none',
                border: '1px solid rgba(0, 229, 255, 0.4)',
                boxShadow: '0 8px 24px rgba(0, 0, 0, 0.2)',
                transition: 'transform 0.2s ease, background-color 0.2s ease',
                cursor: 'pointer',
              }}
              onMouseOver={(e) => {
                e.currentTarget.style.transform = 'translateY(-2px)';
                e.currentTarget.style.backgroundColor = 'rgba(0, 229, 255, 0.15)';
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.transform = 'translateY(0)';
                e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.08)';
              }}
            >
              <span style={{ fontSize: '1.2rem', lineHeight: 1 }}>📱</span>
              Android APK (1-Click)
            </a>
          </div>

          {/* Instant Mobile Try-Out Callout */}
          <div style={{
            width: '100%',
            padding: '1rem 1.25rem',
            borderRadius: '12px',
            backgroundColor: 'rgba(0, 229, 255, 0.06)',
            border: '1px solid rgba(0, 229, 255, 0.2)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '1rem',
            marginBottom: '2rem',
            flexWrap: 'wrap'
          }}>
            <div style={{ flex: '1 1 260px' }}>
              <div style={{ fontWeight: 600, fontSize: '0.95rem', color: '#fff', marginBottom: '0.2rem' }}>
                🚀 Try TchueKAM Mobile on Your Phone Now
              </div>
              <div style={{ fontSize: '0.85rem', color: 'var(--ifm-color-content-secondary)' }}>
                No setup required. Install on iOS or Android directly from your mobile browser.
              </div>
            </div>
            <a
              href="/mobile"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.4rem',
                padding: '0.55rem 1.1rem',
                borderRadius: '8px',
                backgroundColor: '#00E5FF',
                color: '#07070d',
                fontSize: '0.85rem',
                fontWeight: 700,
                textDecoration: 'none',
                whiteSpace: 'nowrap'
              }}
            >
              Try Mobile Version →
            </a>
          </div>

          {/* Multi-Platform Table */}
          <table style={{
            width: '100%',
            borderCollapse: 'collapse',
            textAlign: 'left',
            fontSize: '0.95rem',
            marginBottom: '1.5rem',
          }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.1)' }}>
                <th style={{ padding: '0.75rem 1rem', fontWeight: 600 }}>Platform</th>
                <th style={{ padding: '0.75rem 1rem', fontWeight: 600 }}>File type</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontWeight: 600 }}>Action</th>
              </tr>
            </thead>
            <tbody>
              <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                <td style={{ padding: '0.9rem 1rem', fontWeight: 600 }}>
                  <span style={{ marginRight: '0.4rem' }}>🤖</span> Android (64-bit)
                </td>
                <td style={{ padding: '0.9rem 1rem' }}>
                  <code style={{ padding: '0.2rem 0.4rem', borderRadius: '4px' }}>.apk package</code>
                </td>
                <td style={{ padding: '0.9rem 1rem', textAlign: 'right' }}>
                  <a
                    href="/api/download/android"
                    onClick={handleAndroidDownload}
                    download="TchueKAM-Mobile.apk"
                    style={{ color: '#00E5FF', textDecoration: 'none', fontWeight: 600 }}
                  >
                    1-Click Download →
                  </a>
                </td>
              </tr>
              <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                <td style={{ padding: '0.9rem 1rem', fontWeight: 600 }}>
                  <span style={{ marginRight: '0.4rem' }}>🍎</span> iOS & Mobile Web
                </td>
                <td style={{ padding: '0.9rem 1rem' }}>
                  <code style={{ padding: '0.2rem 0.4rem', borderRadius: '4px' }}>PWA / Add to Home</code>
                </td>
                <td style={{ padding: '0.9rem 1rem', textAlign: 'right' }}>
                  <a
                    href="/mobile"
                    style={{ color: '#00E5FF', textDecoration: 'none', fontWeight: 600 }}
                  >
                    Open & Try →
                  </a>
                </td>
              </tr>
              <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                <td style={{ padding: '0.9rem 1rem', fontWeight: 600 }}>
                  <span style={{ marginRight: '0.4rem' }}>🪟</span> Windows (64-bit)
                </td>
                <td style={{ padding: '0.9rem 1rem' }}>
                  <code style={{ padding: '0.2rem 0.4rem', borderRadius: '4px' }}>.exe installer</code>
                </td>
                <td style={{ padding: '0.9rem 1rem', textAlign: 'right' }}>
                  <a
                    href="/api/download/windows"
                    download="TchueKAM-Setup.exe"
                    style={{ color: '#00E5FF', textDecoration: 'none', fontWeight: 600 }}
                  >
                    Download →
                  </a>
                </td>
              </tr>
              <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                <td style={{ padding: '0.9rem 1rem', fontWeight: 600 }}>
                  <span style={{ marginRight: '0.4rem' }}>🍏</span> macOS (Apple Silicon)
                </td>
                <td style={{ padding: '0.9rem 1rem' }}>
                  <code style={{ padding: '0.2rem 0.4rem', borderRadius: '4px' }}>.dmg</code>
                </td>
                <td style={{ padding: '0.9rem 1rem', textAlign: 'right' }}>
                  <a
                    href="/api/download/mac-arm64"
                    download="TchueKAM-Mac-arm64.dmg"
                    style={{ color: '#00E5FF', textDecoration: 'none', fontWeight: 600 }}
                  >
                    Download →
                  </a>
                </td>
              </tr>
              <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                <td style={{ padding: '0.9rem 1rem', fontWeight: 600 }}>
                  <span style={{ marginRight: '0.4rem' }}>🍏</span> macOS (Intel)
                </td>
                <td style={{ padding: '0.9rem 1rem' }}>
                  <code style={{ padding: '0.2rem 0.4rem', borderRadius: '4px' }}>.dmg</code>
                </td>
                <td style={{ padding: '0.9rem 1rem', textAlign: 'right' }}>
                  <a
                    href="/api/download/mac-x64"
                    download="TchueKAM-Mac-x64.dmg"
                    style={{ color: '#00E5FF', textDecoration: 'none', fontWeight: 600 }}
                  >
                    Download →
                  </a>
                </td>
              </tr>
              <tr>
                <td style={{ padding: '0.9rem 1rem', fontWeight: 600 }}>
                  <span style={{ marginRight: '0.4rem' }}>🐧</span> Linux
                </td>
                <td style={{ padding: '0.9rem 1rem' }}>
                  <code style={{ padding: '0.2rem 0.4rem', borderRadius: '4px' }}>.AppImage</code>
                </td>
                <td style={{ padding: '0.9rem 1rem', textAlign: 'right' }}>
                  <a
                    href="/api/download/linux"
                    download="TchueKAM-Linux.AppImage"
                    style={{ color: '#00E5FF', textDecoration: 'none', fontWeight: 600 }}
                  >
                    Download →
                  </a>
                </td>
              </tr>
            </tbody>
          </table>

          <p style={{
            fontSize: '0.85rem',
            color: 'var(--ifm-color-content-secondary)',
            margin: 0,
            textAlign: 'center',
            opacity: 0.85,
          }}>
            All downloads are verified and hosted directly by TchueKAM.
          </p>
        </div>
      </main>
    </Layout>
  );
}
