import http from 'node:http';
import { createApp } from './app.js';

const PORT = Number(process.env.PORT ?? 8080);
const SHUTDOWN_GRACE_MS = Number(process.env.SHUTDOWN_GRACE_MS ?? 10000);

const { handler, state } = createApp();
const server = http.createServer(handler);
server.keepAliveTimeout = 65000; // longer than typical cloud load balancer idle timeouts (60s)

server.listen(PORT, () => {
  console.log(JSON.stringify({ level: 'info', msg: `algo-visualizer listening on :${PORT}` }));
});

// Graceful shutdown: Kubernetes sends SIGTERM, we fail readiness first so the
// Service stops routing new traffic, finish in-flight requests, then exit.
function shutdown(signal) {
  if (!state.ready) return;
  state.ready = false;
  console.log(JSON.stringify({ level: 'info', msg: `received ${signal}, draining connections` }));
  server.close(() => process.exit(0));
  server.closeIdleConnections?.();
  setTimeout(() => process.exit(1), SHUTDOWN_GRACE_MS).unref();
}
process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
