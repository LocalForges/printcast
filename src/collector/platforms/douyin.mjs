// 抖音平台适配器：把「平台差异」集中在这里（房间号口径、页面地址、是否需要浏览器）。
//
// 采集实现本身仍在 live-collector.mjs（它依赖 CDP、页面脚本、protobuf 解码，
// 拆出去只会增加回归面）；本文件只描述平台「元信息」，让上层不必知道抖音细节。
export const douyin = {
  id: 'douyin',
  label: '抖音',
  // 需要本机浏览器 + 直播间页面才能采到弹幕/礼物/点赞。
  needsBrowser: true,
  needsRoom: true,
  supportsIngest: false,
  roomPattern: /\d{5,25}/,
  hostHint: 'live.douyin.com',
  hint: '弹出本机直播间页面采集，需在该窗口登录抖音；头像抓取更完整。',

  /** 从任意输入（房间号 / 直播链接）抽出房间号，抽不出返回空串。 */
  parseRoom(raw) {
    const text = String(raw == null ? '' : raw);
    const direct = text.match(/(\d{5,25})/);
    return direct ? direct[1] : '';
  },

  /** 直播间页面地址；generic 等无页面平台返回 null。 */
  roomUrl(room) {
    return room ? 'https://live.douyin.com/' + room : null;
  },

  describe() {
    return {
      id: this.id,
      label: this.label,
      needsBrowser: this.needsBrowser,
      needsRoom: this.needsRoom,
      supportsIngest: this.supportsIngest,
      hostHint: this.hostHint,
      hint: this.hint,
    };
  },
};
