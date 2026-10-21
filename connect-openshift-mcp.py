#!/usr/bin/env python3
"""Connect stdio to the existing Red Hat OpenShift MCP service over verified TLS."""
import argparse
import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time


def stop(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--namespace', default='openshift-lightspeed')
    parser.add_argument('--service', default='openshift-mcp-server')
    parser.add_argument('--ca-configmap', default='openshift-service-ca.crt')
    parser.add_argument('--remote-port', type=int, default=8443)
    args = parser.parse_args()
    os.environ['PATH'] = '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:' + os.environ.get('PATH', '')
    oc = shutil.which('oc')
    remote = shutil.which('mcp-remote')
    if not oc or not remote:
        raise RuntimeError('oc and mcp-remote must be installed and available on PATH.')
    context = subprocess.check_output([oc, 'config', 'current-context'], text=True).strip()
    if not context:
        raise RuntimeError('No current kubeconfig context. Log in to the intended cluster first.')
    # Freeze oc operations to this context for this process, even if the default changes.
    oc_args = [oc, '--context', context, '--request-timeout=15s']

    def read(*command):
        result = subprocess.run(oc_args + list(command), capture_output=True, text=True, timeout=25)
        if result.returncode:
            raise RuntimeError('oc ' + ' '.join(command) + ' failed: ' + result.stderr.strip())
        return result.stdout.strip()

    read('whoami')
    api = read('whoami', '--show-server')
    token = read('whoami', '-t')
    if not token:
        raise RuntimeError('This connection needs an OpenShift bearer-token login; run oc login first.')
    service = json.loads(read('get', 'service', args.service, '-n', args.namespace, '-o', 'json'))
    if not any(p['port'] == args.remote_port for p in service['spec']['ports']):
        raise RuntimeError('The service does not expose the configured HTTPS port.')
    ca = json.loads(read('get', 'configmap', args.ca_configmap, '-n', args.namespace, '-o', 'json'))
    ca_pem = ca.get('data', {}).get('service-ca.crt', '')
    if '-----BEGIN CERTIFICATE-----' not in ca_pem:
        raise RuntimeError('The service CA ConfigMap has no service-ca.crt certificate.')

    tunnel = None
    bridge = None
    with tempfile.TemporaryDirectory(prefix='row7-openshift-mcp-') as temp:
        ca_file = Path(temp) / 'service-ca.pem'
        extra_ca = os.environ.get('NODE_EXTRA_CA_CERTS')
        if extra_ca:
            ca_pem += '\n' + Path(extra_ca).read_text()
        ca_file.write_text(ca_pem)
        ca_file.chmod(0o600)
        try:
            tunnel = subprocess.Popen(
                [oc, '--context', context, '-n', args.namespace, 'port-forward',
                 '--address', '127.0.0.1', '--pod-running-timeout=15s',
                 'service/' + args.service, ':' + str(args.remote_port)],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1)
            lines = queue.Queue()

            def drain_tunnel():
                for line in tunnel.stdout:
                    lines.put(line)

            threading.Thread(target=drain_tunnel, daemon=True).start()
            deadline = time.monotonic() + 20
            port = None
            diagnostics = []
            while time.monotonic() < deadline:
                try:
                    line = lines.get(timeout=0.25)
                except queue.Empty:
                    if tunnel.poll() is not None:
                        break
                    continue
                diagnostics.append(line.strip())
                match = re.search(r'Forwarding from 127\.0\.0\.1:(\d+) ->', line)
                if match:
                    port = int(match.group(1))
                    break
            if port is None:
                raise RuntimeError('MCP tunnel did not start: ' + ' '.join(diagnostics[-5:]))

            env = os.environ.copy()
            env.update({
                'OCP_MCP_TUNNEL_PORT': str(port),
                'OCP_MCP_TLS_SERVERNAME': args.service + '.' + args.namespace + '.svc',
                'OCP_MCP_BEARER_TOKEN': token,
                'NODE_EXTRA_CA_CERTS': str(ca_file),
                'MCP_REMOTE_CONFIG_DIR': str(Path(temp) / 'mcp-remote'),
            })
            preload = Path(__file__).with_name('mcp-tunnel-tls.cjs').resolve()
            if not preload.is_file():
                raise RuntimeError('Missing TLS helper: ' + str(preload))
            env['NODE_OPTIONS'] = (env.get('NODE_OPTIONS', '') + ' --require=' + json.dumps(str(preload))).strip()
            print('openshift-mcp: ' + api + ' -> ' + args.namespace + '/' + args.service
                  + ' (private tunnel, verified service TLS)', file=sys.stderr, flush=True)
            bridge = subprocess.Popen(
                [remote, 'https://127.0.0.1:' + str(port) + '/mcp',
                 '--transport', 'http-only', '--header', 'Authorization:Bearer ${OCP_MCP_BEARER_TOKEN}',
                 '--connect-timeout', '15', '--headers-timeout', '30', '--keep-alive'],
                env=env, stdin=sys.stdin, stdout=sys.stdout,
                stderr=subprocess.PIPE, text=True, bufsize=1)

            def drain_bridge():
                for line in bridge.stderr:
                    sys.stderr.write(line.replace(token, '<redacted>'))
                    sys.stderr.flush()

            threading.Thread(target=drain_bridge, daemon=True).start()
            while True:
                try:
                    return bridge.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    if tunnel.poll() is not None:
                        raise RuntimeError('MCP tunnel ended. Reconnect the MCP server in Claude.')
                    # Drain routine port-forward output without accumulating it indefinitely.
                    while not lines.empty():
                        lines.get_nowait()
        finally:
            stop(bridge)
            stop(tunnel)


def interrupted(_signum, _frame):
    raise SystemExit(0)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print('openshift-mcp: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
