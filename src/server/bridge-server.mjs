// 迷你 WebSocket 服务器（仅 stdlib，够本页数据桥用）。
// 支持：握手、文本帧收发、ping/pong、close；客户端帧自动去掩码。
import http from 'node:http';
import crypto from 'node:crypto';

const GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11';

function readFrame(buf) {
  if (buf.length < 2) return null;
  const b1 = buf[1];
  const opcode = buf[0] & 0x0f;
  const masked = (b1 & 0x80) !== 0;
  let len = b1 & 0x7f;
  let off = 2;
  if (len === 126) {
    if (buf.length < 4) return null;
    len = buf.readUInt16BE(2);
    off = 4;
  } else if (len === 127) {
    if (buf.length < 10) return null;
    len = Number(buf.readBigUInt64BE(2));
    off = 10;
  }
  const maskOff = off;
  if (masked) off += 4;
  if (buf.length < off + len) return null;
  let payload = buf.subarray(off, off + len);
  if (masked) {
    const mask = buf.subarray(maskOff, maskOff + 4);
    const un = Buffer.from(payload);
    for (let i = 0; i < un.length; i++) un[i] ^= mask[i & 3];
    payload = un;
  }
  return { opcode, payload, total: off + len };
}

function encodeText(str) {
  const payload = Buffer.from(str, 'utf8');
  const len = payload.length;
  let header;
  if (len < 126) header = Buffer.from([0x81, len]);
  else if (len < 65536) {
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

function controlFrame(opcode, payload = Buffer.alloc(0)) {
  if (payload.length < 126) return Buffer.concat([Buffer.from([0x80 | opcode, payload.length]), payload]);
  const header = Buffer.alloc(4);
  header[0] = 0x80 | opcode;
  header[1] = 126;
  header.writeUInt16BE(payload.length, 2);
  return Buffer.concat([header, payload]);
}

const MAX_INGEST_BYTES = 64 * 1024;

function sendJson(res, code, obj) {
  const body = Buffer.from(JSON.stringify(obj), 'utf8');
  res.writeHead(code, { 'content-type': 'application/json; charset=utf-8', 'content-length': body.length });
  res.end(body);
}

// 通用推流入口：外部平台脚本按事件契约 POST 到这里，事件进入同一条打印通道。
// 这里只做「传输层」职责（方法 / 令牌 / 体积 / JSON 解析），归一化与业务判断
// 交给 onIngest，保证桥服务不依赖采集器的实现细节。
function handleIngest(req, res, onIngest) {
  if (req.method !== 'POST') { sendJson(res, 405, { ok: false, error: '只支持 POST' }); return; }
  const expected = process.env.PRINTCAST_INGEST_TOKEN || '';
  if (expected && String(req.headers['x-ingest-token'] || '') !== expected) {
    sendJson(res, 401, { ok: false, error: '令牌不匹配' });
    return;
  }
  let size = 0;
  const chunks = [];
  let aborted = false;
  req.on('data', chunk => {
    if (aborted) return;
    size += chunk.length;
    if (size > MAX_INGEST_BYTES) {
      aborted = true;
      sendJson(res, 413, { ok: false, error: '请求体超过 ' + MAX_INGEST_BYTES + ' 字节上限' });
      req.destroy();
      return;
    }
    chunks.push(chunk);
  });
  req.on('end', () => {
    if (aborted) return;
    let payload;
    try {
      payload = JSON.parse(Buffer.concat(chunks).toString('utf8') || 'null');
    } catch {
      sendJson(res, 400, { ok: false, error: 'JSON 解析失败' });
      return;
    }
    let result;
    try {
      result = onIngest ? onIngest(payload) : { accepted: 0, rejected: [] };
    } catch (e) {
      sendJson(res, 500, { ok: false, error: String(e && e.message || e) });
      return;
    }
    sendJson(res, 200, {
      ok: true,
      accepted: result.accepted || 0,
      rejected: result.rejected || [],
    });
  });
  req.on('error', () => { if (!aborted) { aborted = true; try { res.destroy() } catch { } } });
}

export function startWSServer(port, { onMessage, onStatus, onError, onIngest, onHealth, identity = null, fallbackPorts = 0 } = {}) {
  const clients = new Set();
  const server = http.createServer((req, res) => {
    const path = String(req.url || '').split('?', 1)[0];
    if (path === '/health') {
      // onHealth 让采集器把平台、统计、最后一帧时间带给控制台；探测方只认
      // service/identity，多出来的字段对老客户端是透明的。
      let extra = {};
      if (onHealth) { try { extra = onHealth() || {} } catch { extra = {} } }
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ service: 'avatar-printer', identity, port: server.address().port, ...extra }));
      return;
    }
    if (path === '/ingest') { handleIngest(req, res, onIngest); return; }
    res.writeHead(200, { 'content-type': 'text/plain; charset=utf-8' });
    res.end('avatar-printer data bridge running');
  });
  let activePort = port;
  server.on('error', err => {
    if (err.code === 'EADDRINUSE' && activePort < port + fallbackPorts) { server.listen(++activePort, '127.0.0.1'); return; }
    if (onError) onError(err);
  });
  server.on('upgrade', (req, sock) => {
    const key = req.headers['sec-websocket-key'];
    if (!key || String(req.headers.upgrade || '').toLowerCase() !== 'websocket') {
      sock.destroy();
      return;
    }
    const accept = crypto.createHash('sha1').update(key + GUID).digest('base64');
    sock.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + accept + '\r\n\r\n');
    sock.setNoDelay(true);
    const client = { sock, buf: Buffer.alloc(0) };
    clients.add(client);
    sock.on('data', d => {
      client.buf = Buffer.concat([client.buf, d]);
      let frame;
      while ((frame = readFrame(client.buf))) {
        client.buf = client.buf.subarray(frame.total);
        if (frame.opcode === 8) {
          try { sock.end(controlFrame(8)) } catch { }
          clients.delete(client);
          return;
        } else if (frame.opcode === 9) {
          try { sock.write(controlFrame(10, frame.payload)) } catch { }
        } else if (frame.opcode === 1 && onMessage) {
          try { onMessage(frame.payload.toString('utf8'), client) } catch { }
        }
      }
    });
    const drop = () => clients.delete(client);
    sock.on('close', drop);
    sock.on('error', drop);
  });
  server.on('clientError', () => { });
  function broadcast(obj) {
    const data = encodeText(JSON.stringify(obj));
    for (const c of [...clients]) {
      try { c.sock.write(data) } catch { clients.delete(c) }
    }
  }
  server.on('listening', () => { if (onStatus) onStatus(server.address().port) });
  server.listen(port, '127.0.0.1');
  return {
    broadcast,
    clientCount: () => clients.size,
    close: () => server.close()
  };
}
