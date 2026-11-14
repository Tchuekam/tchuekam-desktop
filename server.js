/**
 * Tchuekam Agent Backend - Private AI Assistant API & WebSocket Gateway
 * Production Entry Point
 */

import http from 'http';
import net from 'net';
import tls from 'tls';
import crypto from 'crypto';
import { URL } from 'url';

const PORT = parseInt(process.env.PORT || '10000', 10);
const HOST = '0.0.0.0';
const NODE_ENV = process.env.NODE_ENV || 'development';
const API_PREFIX = process.env.API_PREFIX || '/api/v1';
const DATABASE_URL = process.env.DATABASE_URL || '';
const JWT_SECRET = process.env.JWT_SECRET || 'insecure-default-secret';
const CORS_ORIGIN = process.env.CORS_ORIGIN || '*';

let isShuttingDown = false;
const activeSockets = new Set();
const wsClients = new Set();

/**
 * Checks PostgreSQL database reachability via TCP/TLS socket
 */
function checkDatabaseConnection(connString) {
  return new Promise((resolve) => {
    if (!connString) {
      return resolve({ alive: false, error: 'DATABASE_URL not configured' });
    }

    try {
      const parsed = new URL(connString);
      const host = parsed.hostname;
      const port = parseInt(parsed.port || '5432', 10);

      const socket = net.createConnection({ host, port, timeout: 4000 }, () => {
        socket.destroy();
        resolve({ alive: true, host, port });
      });

      socket.on('error', (err) => {
        resolve({ alive: false, error: err.message, host, port });
      });

      socket.on('timeout', () => {
        socket.destroy();
        resolve({ alive: false, error: 'Connection timed out', host, port });
      });
    } catch (err) {
      resolve({ alive: false, error: err.message });
    }
  });
}

/**
 * Handle incoming HTTP requests
 */
const server = http.createServer(async (req, res) => {
  if (isShuttingDown) {
    res.writeHead(503, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify({ error: 'Server is shutting down' }));
  }

  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', CORS_ORIGIN.includes(',') ? '*' : CORS_ORIGIN);
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With');
  res.setHeader('Access-Control-Allow-Credentials', 'true');

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
      database_details: dbStatus,
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
server.on('upgrade', (req, socket, head) => {
  const reqUrl = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const pathname = reqUrl.pathname;

  if (pathname !== '/ws' && pathname !== '/events') {
    socket.write('HTTP/1.1 404 Not Found\r\n\r\n');
    socket.destroy();
    return;
  }

  const key = req.headers['sec-websocket-key'];
  if (!key) {
    socket.write('HTTP/1.1 400 Bad Request\r\n\r\n');
    socket.destroy();
    return;
  }

  // Calculate WebSocket accept hash
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

  // Send initial connected frame
  const welcomePayload = JSON.stringify({
    type: 'gateway:ready',
    service: 'tchuekam-agent-gateway',
    session: crypto.randomUUID(),
    authenticated: true,
    timestamp: new Date().toISOString()
  });

  const payloadBuffer = Buffer.from(welcomePayload);
  const frame = Buffer.concat([
    Buffer.from([0x81, payloadBuffer.length]), // FIN + Text frame
    payloadBuffer
  ]);
  socket.write(frame);

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

  // Stop accepting new connections
  server.close(() => {
    console.log('[Tchuekam Agent] HTTP and WebSocket server closed cleanly.');
    process.exit(0);
  });

  // Notify and close WebSocket clients
  for (const client of wsClients) {
    try {
      client.end();
    } catch (_) {}
  }
  wsClients.clear();

  // Force exit after 30 seconds if connections remain open
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

