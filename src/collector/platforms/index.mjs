// 平台注册表：新增平台 = 加一个 adapter 模块 + 在这里登记一行。
//
// 上层只通过 resolvePlatform() 取平台，不 import 具体平台文件，
// 因此将来加 bilibili / kuaishou 只需扩这里，采集主流程不动。
import { douyin } from './douyin.mjs';
import { generic } from './generic.mjs';

const REGISTRY = new Map([
  [douyin.id, douyin],
  [generic.id, generic],
]);

export const DEFAULT_PLATFORM = 'douyin';

/** 列出全部平台（给控制台下拉与 /__api 用）。 */
export function listPlatforms() {
  return [...REGISTRY.values()].map(p => p.describe());
}

export function platformIds() {
  return [...REGISTRY.keys()];
}

/**
 * 解析平台 id；未知 id 回落到默认平台而不是抛错——
 * 老配置里写着 'other' 之类的值时，服务仍要能起来。
 */
export function resolvePlatform(id) {
  const key = String(id == null ? '' : id).trim().toLowerCase();
  return REGISTRY.get(key) || REGISTRY.get(DEFAULT_PLATFORM);
}

export { douyin, generic };
