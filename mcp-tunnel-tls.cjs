// Verify the real service's TLS identity through an authenticated oc tunnel.
// The HTTP Host remains loopback, as required by the server's localhost protection.
const tls = require('node:tls');
const { syncBuiltinESMExports } = require('node:module');
const connect = tls.connect;
const port = Number(process.env.OCP_MCP_TUNNEL_PORT);
const servername = process.env.OCP_MCP_TLS_SERVERNAME;

tls.connect = function (...args) {
  const options = args[0];
  if (servername && options && typeof options === 'object'
      && Number(options.port) === port
      && ['127.0.0.1', 'localhost'].includes(options.host || options.hostname)) {
    args[0] = { ...options, servername, rejectUnauthorized: true };
  }
  return connect.apply(this, args);
};
syncBuiltinESMExports();
