// 采集层纯函数：弹幕行解析、礼物归类、昵称清洗、protobuf 解码、头像 URL 判定、新行 diff、点赞公平分配。
// 全部无副作用、不依赖 DOM / 文件系统 / 进程状态，可被 Node 测试直接 import。

// —— 纯解析函数（供测试） ——

export function parseChatLine(raw) {
    const text = String(raw || '').replace(/\s+/g, ' ').trim();
    if (!text) return null;
    if (/欢迎来到直播间|严禁|未成年人|网络诈骗|理性消费|新功能|三屏|点击体验/.test(text) || /^(新功能|提示|公告|系统)\s*[：:]/.test(text)) return {
        kind: 'system',
        text
    };
    let m = text.match(/^(.{1,24}?)\s*[：:]\s*(.*)$/);
    if (m) {
        const name = m[1].trim(), body = m[2].trim();
        if (!name || isJunkName(name)) return null;
        const g = body.match(/^(?:送出|送了|送给主播)了?\s*(.+?)(?:\s*[xX×]\s*(\d{1,3}))?$/);
        if (g && g[1].trim()) return {kind: 'gift', name, gift: g[1].trim(), count: g[2] ? +g[2] : 1};
        if (/^(关注了主播|关注了直播间|成为新粉丝)/.test(body)) return {kind: 'follow', name};
        if (!body) return null;
        return {kind: 'comment', name, text: body};
    }
    m = text.match(/^(.{1,24}?)\s*(?:送出|送了|送给主播)了?\s*(.+?)(?:\s*[xX×]\s*(\d{1,3}))?$/);
    if (m && m[2].trim() && !isJunkName(m[1].trim())) return {
        kind: 'gift',
        name: m[1].trim(),
        gift: m[2].trim(),
        count: m[3] ? +m[3] : 1
    };
    m = text.match(/^(.{1,20}?)\s*来了$/);
    if (m) return {kind: 'join', name: m[1].trim()};
    m = text.match(/^(.{1,24}?)\s*(?:关注了主播|关注了直播间|成为新粉丝|推荐了直播)/);
    if (m) return {kind: 'follow', name: m[1].trim()};
    return null;
}

export function mapGift(name) {
    if (/啤酒/.test(name)) return 'beer';
    if (/棒棒糖/.test(name)) return 'lollipop';
    if (/爱心|红心|心心/.test(name)) return 'heart';
    return 'other';
}

// 垃圾名判定：feed卡标签、动作短语等不是观众昵称。
export function isJunkName(n) {
    if (!n) return true;
    const s = String(n);
    if (/充钻石|客户端|壁纸通知|消息投稿|互相关注|粉丝团|账号已在其他地方|进入直播间|扫码登录/.test(s)) return true;
    if (s.length < 1 || s.length > 24) return true;
    if (/^(送出了?|送了|来了|关注|粉丝|评论|分享|关注了.*)$/.test(s)) return true;
    if (/分享\[视频\]|前天分享|小时榜|人气榜|本场点赞|在线观众|贡献/.test(s)) return true;
    if (!/[\u{4e00}-\u{9fff}a-zA-Z]/u.test(s)) return true;
    return false;
}

// 昵称归一化：去掉空格与装饰 emoji，用于弹幕昵称 ↔ 观众面板头像的模糊匹配。
export function normKey(name) {
    return String(name || '').replace(/[\s\u3000]+/g, '').replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}\u{2B00}-\u{2BFF}]/gu, '');
}

// —— 协议级解码：通用 protobuf 遍历 + 直播间 WebSocket 帧 → 用户(昵称,头像) ——
export function pbDecode(buf) {
    const fields = [];
    let i = 0;
    try {
        while (i < buf.length) {
            let key = 0, shift = 0, byte;
            do {
                if (i >= buf.length) return fields;
                byte = buf[i++];
                key |= (byte & 0x7f) << shift;
                shift += 7;
                if (shift > 35) return fields;
            } while (byte & 0x80);
            const fieldNum = key >>> 3, wire = key & 7;
            if (fieldNum === 0) return fields;
            if (wire === 0) {
                let v = 0n, s = 0n;
                do {
                    if (i >= buf.length) return fields;
                    byte = buf[i++];
                    v |= BigInt(byte & 0x7f) << s;
                    s += 7n;
                } while (byte & 0x80);
                fields.push({n: fieldNum, wire, num: v});
            } else if (wire === 1) {
                if (i + 8 > buf.length) return fields;
                i += 8;
                fields.push({n: fieldNum, wire, buf: buf.subarray(i - 8, i)});
            } else if (wire === 2) {
                let len = 0, sh = 0;
                do {
                    if (i >= buf.length) return fields;
                    byte = buf[i++];
                    len |= (byte & 0x7f) << sh;
                    sh += 7;
                } while (byte & 0x80);
                if (i + len > buf.length) return fields;
                fields.push({n: fieldNum, wire, buf: buf.subarray(i, i + len)});
                i += len;
            } else if (wire === 5) {
                if (i + 4 > buf.length) return fields;
                i += 4;
                fields.push({n: fieldNum, wire, buf: buf.subarray(i - 4, i)});
            } else return fields;
        }
    } catch {
    }
    return fields;
}

function imageUrl(buf, depth = 0) {
    if (depth > 5) return '';
    const text = buf.toString('utf8');
    if (/^https?:\/\/[^\s]+$/.test(text) && /douyinpic|byteimg|douyinstatic/.test(text)) return text;
    for (const field of pbDecode(buf)) {
        if (field.wire !== 2 || !field.buf) continue;
        const url = imageUrl(field.buf, depth + 1);
        if (url) return url;
    }
    return '';
}

// 头像 URL 特征：aweme 用户头像或 webcast 用户头像；勋章/等级/标签/礼物图一律不算。
export function isExplicitAvatarUrl(u) {
    return /(aweme-avatar|tos-cn-avt|\/aweme\/100x100\/|sc=avatar)/i.test(String(u || ''));
}

export function isAvatarUrl(u) {
    const s = String(u || '');
    if (!s) return false;
    if (/(aweme-avatar|\/aweme\/100x100\/|sc=avatar)/i.test(s)) return true;
    return /img\/webcast\/[a-f0-9]{16,}\./i.test(s) && !/(grade|badge|medal|icon|label|gift|effect|frame|banner)/i.test(s);
}

// 递归收集缓冲里所有"User 形状"的结构：#3 是昵称，#9/10/11/6 内嵌头像 URL。
// 注意不能在消息体顶层找 #3——ChatMessage 的 #3 是弹幕文本，会张冠李戴。
export function collectUsers(buf, depth = 0) {
    const out = [];
    if (depth > 8) return out;
    const fields = pbDecode(buf);
    const nickname = fields.find(f => f.n === 3 && f.wire === 2)?.buf?.toString('utf8');
    if (nickname && nickname.length <= 40 && !/[\x00-\x1f\ufffd]/.test(nickname) && !/^https?:/.test(nickname)) {
        for (const n of [9, 10, 11, 6]) {
            const field = fields.find(f => f.n === n && f.wire === 2);
            const avatar = field?.buf && imageUrl(field.buf);
            if (avatar && isAvatarUrl(avatar)) {
                out.push({name: nickname, avatar});
                break;
            }
        }
    }
    for (const f of fields) {
        if (f.wire !== 2 || !f.buf?.length || f.buf.length < 16) continue;
        out.push(...collectUsers(f.buf, depth + 1));
    }
    return out;
}

export function extractUser(buf, depth = 0) {
    return collectUsers(buf, depth)[0] || null;
}

// 从 gzip 解包后的 protobuf 里找出所有 {方法名, 消息体} 信封再回调。
// 信封特征：#1 恰好是 "WebcastXxxMessage" 字符串、#2 是消息体。
// 绝不能用"头部含 Webcast 字样"来匹配——每条消息体内部的 Common 结构也嵌着同名方法串，
// 旧代码因此把真正的消息体也当方法串跳过，协议级解码从未命中过一条消息。
export function eachEnvelope(buf, cb, depth = 0) {
    if (depth > 4) return;
    for (const f of pbDecode(buf)) {
        if (f.wire !== 2 || !f.buf || f.buf.length < 24) continue;
        const sub = pbDecode(f.buf);
        const method = sub.find(s => s.n === 1 && s.wire === 2)?.buf?.toString('utf8');
        if (method && /^Webcast\w{1,30}Message$/.test(method)) {
            const pl = sub.find(s => s.n === 2 && s.wire === 2 && s.buf && s.buf.length >= 12);
            if (pl) {
                cb(method, pl.buf);
                continue;
            }
        }
        if (f.buf.length > 40) eachEnvelope(f.buf, cb, depth + 1);
    }
}

// 从页面文本里抽"本场点赞"计数，支持 "1.2万" 这类写法。
export function parseLike(text) {
    const m = String(text || '').match(/([\d.]+)(万)?\s*本场点赞/);
    if (!m) return null;
    const v = parseFloat(m[1]);
    if (!isFinite(v)) return null;
    return Math.round(v * (m[2] ? 10000 : 1));
}

export function diffNew(lines, seen, cap = 80) {
    const fresh = [];
    for (let i = lines.length - 1; i >= 0 && fresh.length < cap; i--) {
        if (seen.has(lines[i])) break;
        fresh.unshift(lines[i]);
    }
    for (const sig of fresh) seen.add(sig);
    while (seen.size > 600) seen.delete(seen.values().next().value);
    return fresh;
}

// 点赞无法从页面获知点赞人：在累积观众花名册上公平轮换，同一人最多连续 cap 次，
// 所有人用满后开新一轮；一轮内打不完的点赞直接丢弃（避免同一人刷屏）。
export function allocateLikes(delta, roster, state, cap = 3) {
    const events = [];
    let assigned = 0, passes = 0;
    const capFor = e => (e[1] ? cap : 1);
    const maxScan = roster.reduce((s, e) => s + capFor(e), 0);
    while (assigned < delta && passes < 2 && roster.length) {
        let scanned = 0;
        while (assigned < delta && scanned < maxScan) {
            if (state.idx >= roster.length) state.idx = 0;
            const entry = roster[state.idx];
            state.idx = (state.idx + 1) % roster.length;
            scanned++;
            const used = state.used.get(entry[0]) || 0;
            if (used >= capFor(entry)) continue;
            state.used.set(entry[0], used + 1);
            const last = events[events.length - 1];
            if (last && last.name === entry[0]) last.count++;
            else events.push({name: entry[0], avatar: entry[1], count: 1});
            assigned++;
        }
        if (assigned < delta) {
            state.used.clear();
            passes++;
        } else break;
    }
    return events;
}
