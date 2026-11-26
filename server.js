/**
 * Tchuekam Agent — minimal HTTP/WebSocket edge shim.
 *
 * NOT THE API. This file serves exactly four things: /healthz, /health,
 * /api/v1/status, and a WebSocket upgrade on /ws and /events that emits a
 * "gateway:ready" frame. Every other path returns 404. It has no
 * authentication, no users, no RBAC, no organizations, and it never opens a
 * database connection — it only TCP-pings DATABASE_URL for the health check.
 *
 * The real multi-tenant API is the Python FastAPI application in
 * tchuekam_backend/ (auth, RBAC, organizations, workspaces, teams,
 * invitations, API keys, files, audit). Serve it with:
 *
 *     gunicorn -c gunicorn.conf.py tchuekam_backend.main:app
 *
 * render.yaml used to deploy THIS file as "tchuekam-agent-api" via
 * `npm run start:prod`, so a deploy from that blueprint came up reporting
 * healthy with no API behind it. All deploy descriptors now point at the
 * Python app; see docs/CAPACITY.md.
 *
 * Keep this shim only for a deliberately dependency-free health/WS endpoint.
 * Do not add API routes here — they belong in tchuekam_backend/.
 */

import http from 'http';
import net from 'net';
import crypto from 'crypto';
import { URL } from 'url';

const PORT = parseInt(process.env.PORT || '10000', 10);
const HOST = '0.0.0.0';
const NODE_ENV = process.env.NODE_ENV || 'development';
const IS_PRODUCTION = NODE_ENV === 'production';
const API_PREFIX = process.env.API_PREFIX || '/api/v1';
const DATABASE_URL = process.env.DATABASE_URL || '';

const configuredJwtSecret = (process.env.JWT_SECRET || '').trim();
if (IS_PRODUCTION && configuredJwtSecret.length < 32) {
  throw new Error('JWT_SECRET must be set and at least 32 characters in production.');
}
const JWT_SECRET = configuredJwtSecret || crypto.randomBytes(48).toString('base64url');
void JWT_SECRET;

const GATEWAY_TOKEN = (process.env.GATEWAY_TOKEN || '').trim();
const ALLOWED_ORIGINS = (process.env.CORS_ORIGIN || '')
  .split(',')
  .map((o) => o.trim().replace(/\/+$/, ''))
  .filter((o) => o && o !== '*');

let isShuttingDown = false;
const activeSockets = new Set();
const wsClients = new Set();

function isOriginAllowed(origin) {
  if (!origin) return true;
  const cleanOrigin = origin.trim().replace(/\/+$/, '');
  return ALLOWED_ORIGINS.includes(cleanOrigin);
}

function timingSafeEqualStr(a, b) {
  const bufA = Buffer.from(a, 'utf8');
  const bufB = Buffer.from(b, 'utf8');
  if (bufA.length !== bufB.length) return false;
  return crypto.timingSafeEqual(bufA, bufB);
}

function buildWsTextFrame(text) {
  const payload = Buffer.from(text, 'utf8');
  const len = payload.length;
  let header;
  if (len < 126) {
    header = Buffer.from([0x81, len]);
  } else if (len <= 0xffff) {
    header = Buffer.alloc(4);
    header[0] = 0x81;
    header[1] = 126;
    header.writeUInt16BE(len, 2);
  } else {
    header = Buffer.alloc(10);
    header[0] = 0x81;
    header[1] = 127;
    header.writeBigUInt64BE(BigInt(len), 2);
  }
  return Buffer.concat([header, payload]);
}

function applySecurityHeaders(res) {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
}

/**
 * Checks PostgreSQL database reachability via TCP/TLS socket
 */
function checkDatabaseConnection(connString) {
  return new Promise((resolve) => {
    if (!connString) {
      return resolve({ alive: false });
    }

    try {
      const parsed = new URL(connString);
      const host = parsed.hostname;
      const port = parseInt(parsed.port || '5432', 10);

      const socket = net.createConnection({ host, port, timeout: 4000 }, () => {
        socket.destroy();
        resolve({ alive: true });
      });

      socket.on('error', () => {
        resolve({ alive: false });
      });

      socket.on('timeout', () => {
        socket.destroy();
        resolve({ alive: false });
      });
    } catch {
      resolve({ alive: false });
    }
  });
}

/**
 * Handle incoming HTTP requests
 */
const server = http.createServer(async (req, res) => {
  applySecurityHeaders(res);

  if (isShuttingDown) {
    res.writeHead(503, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify({ error: 'Server is shutting down' }));
  }

  const origin = req.headers.origin;
  if (origin && ALLOWED_ORIGINS.includes(origin.trim().replace(/\/+$/, ''))) {
    res.setHeader('Access-Control-Allow-Origin', origin.trim());
    res.setHeader('Access-Control-Allow-Credentials', 'true');
    res.setHeader('Vary', 'Origin');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With');
  }

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    return res.end();
  }

  const reqUrl = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const pathname = reqUrl.pathname;

  // Health check endpoint
  if (pathname === '/healthz' || pathname === '/health') {
    const dbStatus = await checkDatabaseConnection(DATABASE_URL);
    const isHealthy = !DATABASE_URL || dbStatus.alive;
    const statusCode = isHealthy ? 200 : 503;

    res.writeHead(statusCode, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify({
      status: isHealthy ? 'healthy' : 'degraded',
      service: 'tchuekam-agent-api',
      database: dbStatus.alive ? 'alive' : 'disconnected',
      environment: NODE_ENV,
      version: '1.0.0',
      uptime_seconds: process.uptime(),
      timestamp: new Date().toISOString()
    }, null, 2));
  }

  // API prefix routes
  if (pathname === `${API_PREFIX}/status` || pathname === '/api/status' || pathname === '/') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify({
      name: 'Tchuekam Agent API & WebSocket Gateway',
      status: 'operational',
      environment: NODE_ENV,
      api_prefix: API_PREFIX,
      transport: ['http', 'websocket'],
      endpoints: {
        health: '/healthz',
        status: `${API_PREFIX}/status`,
        websocket: '/ws',
        events: '/events'
      },
      timestamp: new Date().toISOString()
    }, null, 2));
  }

  // Fallback 404
  res.writeHead(404, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ error: 'Not Found', path: pathname }));
});

// Track sockets for graceful termination
server.on('connection', (socket) => {
  activeSockets.add(socket);
  socket.on('close', () => activeSockets.delete(socket));
});

/**
 * Native RFC 6455 WebSocket Gateway Upgrade Handler for /ws and /events
 */
server.on('upgrade', (req, socket) => {
  const reqUrl = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const pathname = reqUrl.pathname;

  if (pathname !== '/ws' && pathname !== '/events') {
    socket.write('HTTP/1.1 404 Not Found\r\n\r\n');
    socket.destroy();
    return;
  }

  const origin = req.headers.origin;
  if (origin && !isOriginAllowed(origin)) {
    socket.write('HTTP/1.1 403 Forbidden\r\n\r\n');
    socket.destroy();
    return;
  }

  let isAuthenticated = false;
  if (GATEWAY_TOKEN) {
    const authHeader = req.headers.authorization || '';
    const bearer = authHeader.startsWith('Bearer ') ? authHeader.slice(7).trim() : '';
    const queryTok = (reqUrl.searchParams.get('token') || '').trim();
    const candidate = bearer || queryTok;
    if (!candidate || !timingSafeEqualStr(candidate, GATEWAY_TOKEN)) {
      socket.write('HTTP/1.1 401 Unauthorized\r\n\r\n');
      socket.destroy();
      return;
    }
    isAuthenticated = true;
  }

  const key = req.headers['sec-websocket-key'];
  if (!key) {
    socket.write('HTTP/1.1 400 Bad Request\r\n\r\n');
    socket.destroy();
    return;
  }

  const GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11';
  const acceptKey = crypto.createHash('sha1').update(key + GUID).digest('base64');

  const responseHeaders = [
    'HTTP/1.1 101 Switching Protocols',
    'Upgrade: websocket',
    'Connection: Upgrade',
    `Sec-WebSocket-Accept: ${acceptKey}`
  ];

  socket.write(responseHeaders.join('\r\n') + '\r\n\r\n');
  wsClients.add(socket);

  const welcomePayload = JSON.stringify({
    type: 'gateway:ready',
    service: 'tchuekam-agent-gateway',
    session: crypto.randomUUID(),
    authenticated: isAuthenticated,
    timestamp: new Date().toISOString()
  });

  socket.write(buildWsTextFrame(welcomePayload));

  socket.on('close', () => wsClients.delete(socket));
  socket.on('error', () => {
    wsClients.delete(socket);
    socket.destroy();
  });
});

/**
 * Start Server
 */
server.listen(PORT, HOST, () => {
  console.log(`[Tchuekam Agent] Production API & WebSocket Gateway listening on http://${HOST}:${PORT}`);
  console.log(`[Tchuekam Agent] Environment: ${NODE_ENV} | API Prefix: ${API_PREFIX}`);
  console.log(`[Tchuekam Agent] Healthcheck: http://${HOST}:${PORT}/healthz`);
});

/**
 * Graceful Shutdown (SIGTERM & SIGINT) with 30s timeout
 */
function gracefulShutdown(signal) {
  console.log(`\n[Tchuekam Agent] Received ${signal}. Commencing graceful shutdown (30s grace period)...`);
  isShuttingDown = true;

  server.close(() => {
    console.log('[Tchuekam Agent] HTTP and WebSocket server closed cleanly.');
    process.exit(0);
  });

  for (const client of wsClients) {
    try {
      client.end();
    } catch (_) {}
  }
  wsClients.clear();

  const shutdownTimer = setTimeout(() => {
    console.warn('[Tchuekam Agent] Graceful shutdown timeout reached (30s). Forcing socket closure...');
    for (const socket of activeSockets) {
      try {
        socket.destroy();
      } catch (_) {}
    }
    process.exit(0);
  }, 30000);

  shutdownTimer.unref();
}

process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
process.on('SIGINT', () => gracefulShutdown('SIGINT'));
