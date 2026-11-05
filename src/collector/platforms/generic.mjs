// 通用推流平台：不驱动浏览器，只开着数据桥等外部按契约 v1 推事件进来。
//
// 这是「后期平台扩展」的落点：接入 B 站 / 快手 / 视频号 / 自建弹幕源时，
// 不需要改本仓库，只要写一个脚本把事件 POST 到 /ingest 即可：
//
//   curl -s http://127.0.0.1:8765/ingest \
//     -H 'content-type: application/json' \
//     -H 'x-ingest-token: <可选，设了 PRINTCAST_INGEST_TOKEN 才需要>' \
//     -d '{"type":"comment","name":"小明","text":"打印我","avatar":"https://…/a.jpg"}'
export const generic = {
  id: 'generic',
  label: '通用推流',
  needsBrowser: false,
  needsRoom: false,
  supportsIngest: true,
  roomPattern: null,
  hostHint: '',
  hint: '不开浏览器，等外部脚本按事件契约推流（B 站/快手/自建弹幕源均可接入）。',

  parseRoom() { return ''; },

  roomUrl() { return null; },

  describe() {
    return {
      id: this.id,
      label: this.label,
      needsBrowser: this.needsBrowser,
      needsRoom: this.needsRoom,
      supportsIngest: this.supportsIngest,
      ingestPath: '/ingest',
      hint: this.hint,
    };
  },
};
