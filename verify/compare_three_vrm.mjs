// 元の VRM1 と変換後の VRM0 を three-vrm（aituber-kit と同じ版）で同じ条件で動かして比べる。
//   node verify/compare_three_vrm.mjs <vrm1> <vrm0> [--report <変換レポート.json>] [--json out.json]
// 比較はすべて「キャラクター基準の座標」（左・上・前）で行う。VRM0 は aituber-kit と同じく rotateVRM0 する。
// --report を渡すと、レポートが lossy / needs_decision として既に書いている揺れもの（関節の値の違い・
// 入れ子・左右向きの重力など）のずれは「申告済み」として分けて出し、失敗に数えない。
import { register } from 'node:module';
import fs from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

// three と three-vrm は verify/node_modules から読む。THREE_VRM_FROM で、それらが入った別のプロジェクトの package.json を指せる。
const parentURL = process.env.THREE_VRM_FROM
  ? pathToFileURL(process.env.THREE_VRM_FROM).href
  : new URL('./package.json', import.meta.url).href;
register(
  'data:text/javascript,' +
    encodeURIComponent(
      `const P=${JSON.stringify(parentURL)};` +
        `export async function resolve(s,c,next){` +
        `if(s==='three'||s.startsWith('three/')||s.startsWith('@pixiv/'))return next(s,{...c,parentURL:P});` +
        `return next(s,c);}`
    ),
  import.meta.url
);

const THREE = await import('three');
const { GLTFLoader } = await import('three/examples/jsm/loaders/GLTFLoader.js');
const { VRMLoaderPlugin, VRMUtils } = await import('@pixiv/three-vrm');

const FPS = 60;
const DT = 1 / FPS;
// motionRatio: 体を揺らしたときの先端の動きの大きさの比（小さい方/大きい方）がこれ未満なら、片方が動いていない
const LIMITS = { restDeg: 5, motionCos: 0.9, motionRatio: 0.5, morph: 1e-3, lookAtMm: 1 };

// ---- GLB の読み書き（テクスチャを外して Node でも読めるようにする） ----
function readGlb(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let json = null;
  let bin = new Uint8Array();
  for (let o = 12; o < bytes.byteLength; ) {
    const length = view.getUint32(o, true);
    const type = view.getUint32(o + 4, true);
    const chunk = bytes.subarray(o + 8, o + 8 + length);
    if (type === 0x4e4f534a) json = JSON.parse(new TextDecoder().decode(chunk));
    if (type === 0x004e4942) bin = chunk;
    o += 8 + length;
  }
  return { json, bin };
}

function writeGlb(json, bin) {
  const pad = (n) => (4 - (n % 4)) % 4;
  let text = new TextEncoder().encode(JSON.stringify(json));
  text = Uint8Array.from([...text, ...new Array(pad(text.length)).fill(0x20)]);
  const binPadded = new Uint8Array(bin.length + pad(bin.length));
  binPadded.set(bin);
  const total = 12 + 8 + text.length + (binPadded.length ? 8 + binPadded.length : 0);
  const out = new Uint8Array(total);
  const view = new DataView(out.buffer);
  view.setUint32(0, 0x46546c67, true);
  view.setUint32(4, 2, true);
  view.setUint32(8, total, true);
  view.setUint32(12, text.length, true);
  view.setUint32(16, 0x4e4f534a, true);
  out.set(text, 20);
  if (binPadded.length) {
    const o = 20 + text.length;
    view.setUint32(o, binPadded.length, true);
    view.setUint32(o + 4, 0x004e4942, true);
    out.set(binPadded, o + 8);
  }
  return out;
}

const DROP_EXTENSIONS = ['VRMC_materials_mtoon', 'KHR_texture_transform', 'KHR_materials_unlit', 'KHR_materials_emissive_strength', 'VRMC_materials_hdr_emissiveMultiplier'];

function geometryOnly(bytes) {
  const { json, bin } = readGlb(bytes);
  const copy = structuredClone(json);
  copy.materials = (copy.materials ?? []).map((m) => ({ name: m.name, pbrMetallicRoughness: { baseColorFactor: [1, 1, 1, 1] } }));
  delete copy.images;
  delete copy.textures;
  delete copy.samplers;
  copy.extensionsUsed = (copy.extensionsUsed ?? []).filter((x) => !DROP_EXTENSIONS.includes(x));
  copy.extensionsRequired = (copy.extensionsRequired ?? []).filter((x) => !DROP_EXTENSIONS.includes(x));
  const vrm0 = copy.extensions?.VRM;
  if (vrm0) {
    delete vrm0.meta?.texture;
    for (const mp of vrm0.materialProperties ?? []) {
      mp.textureProperties = {};
      mp.shader = 'VRM_USE_GLTFSHADER';
    }
  }
  if (copy.extensions?.VRMC_vrm?.meta) delete copy.extensions.VRMC_vrm.meta.thumbnailImage;
  return writeGlb(copy, bin);
}

async function loadVrm(path) {
  const bytes = new Uint8Array(await fs.readFile(path));
  const glb = geometryOnly(bytes);
  const loader = new GLTFLoader();
  loader.register((parser) => new VRMLoaderPlugin(parser));
  const gltf = await loader.parseAsync(glb.buffer, '');
  const vrm = gltf.userData.vrm;
  if (!vrm) throw new Error(`VRM として読めません: ${path}`);
  if (vrm.meta?.metaVersion === '0') VRMUtils.rotateVRM0(vrm);
  // 体ごと動かすための入れ物。正規化された骨の軸は VRM0 と VRM1 で向きが違うため、骨ではなくこれを動かす。
  const rig = new THREE.Group();
  rig.add(vrm.scene);
  rig.updateMatrixWorld(true);
  if (vrm.lookAt) vrm.lookAt.autoUpdate = false;
  return { vrm, rig, json: readGlb(bytes).json };
}

// ---- キャラクター基準の座標 ----
function characterFrame(vrm) {
  vrm.scene.parent?.updateMatrixWorld(true);
  const pos = (name) => vrm.humanoid.getRawBoneNode(name).getWorldPosition(new THREE.Vector3());
  const hips = pos('hips');
  const left = pos('leftUpperLeg').sub(pos('rightUpperLeg')).normalize();
  const up0 = pos('head').sub(hips).normalize();
  const forward = new THREE.Vector3().crossVectors(left, up0).normalize();
  const up = new THREE.Vector3().crossVectors(forward, left).normalize();
  const toLocal = new THREE.Matrix4().makeBasis(left, up, forward).setPosition(hips).invert();
  return {
    point: (p) => p.clone().applyMatrix4(toLocal),
    dir: (d) => d.clone().transformDirection(toLocal),
  };
}

// ---- 揺れもの ----
function springJoints(vrm) {
  const map = new Map();
  for (const joint of vrm.springBoneManager?.joints ?? []) {
    if (joint.child) map.set(joint.bone.name, joint);
  }
  return map;
}

function jointDirections(vrm, joints, frame) {
  vrm.scene.parent?.updateMatrixWorld(true);
  const result = new Map();
  for (const [name, joint] of joints) {
    const a = joint.bone.getWorldPosition(new THREE.Vector3());
    const b = joint.child.getWorldPosition(new THREE.Vector3());
    result.set(name, { dir: frame.dir(b.clone().sub(a)).normalize(), tip: frame.point(b) });
  }
  return result;
}

function shake(rig, frameIndex) {
  const t = frameIndex * DT;
  rig.position.set(Math.sin(t * 9) * 0.12, Math.sin(t * 11) * 0.05, Math.cos(t * 8) * 0.08);
  rig.rotation.set(Math.cos(t * 6) * 0.2, Math.sin(t * 7) * 0.4, Math.sin(t * 10) * 0.25);
  rig.updateMatrixWorld(true);
}

function simulate({ vrm, rig }) {
  const joints = springJoints(vrm);
  vrm.springBoneManager?.reset();
  for (let f = 0; f < FPS * 3; f++) vrm.update(DT);
  const frame = characterFrame(vrm);
  const rest = jointDirections(vrm, joints, frame);
  for (let f = 0; f < 90; f++) {
    shake(rig, f);
    vrm.update(DT);
  }
  const moved = jointDirections(vrm, joints, characterFrame(vrm));
  return { joints, rest, moved };
}

const deg = (a, b) => (a.angleTo(b) * 180) / Math.PI;

// レポートが申告済みの揺れもの（spring 名）→ その関節の骨名
function declaredJoints(vrm1Json, reportPath) {
  const names = new Set();
  if (!reportPath) return names;
  const report = JSON.parse(readFileSync(reportPath, 'utf8'));
  const springs = new Set(
    report.items.filter((i) => i.section === 'spring' && i.kind !== 'info').map((i) => i.target)
  );
  for (const spring of vrm1Json.extensions?.VRMC_springBone?.springs ?? []) {
    if (!springs.has(spring.name)) continue;
    for (const joint of spring.joints) names.add(vrm1Json.nodes[joint.node].name);
  }
  return names;
}

function compareSprings(l1, l0, declared, failures, details) {
  const s1 = simulate(l1);
  const s0 = simulate(l0);
  const kept = [];
  const declaredDiffs = [];
  const missing = [];
  for (const [name, r1] of s1.rest) {
    const r0 = s0.rest.get(name);
    if (!r0) {
      if (declared.has(name)) declaredDiffs.push({ name, missing: true });
      else missing.push(name);
      continue;
    }
    const m1 = s1.moved.get(name).tip.clone().sub(r1.tip);
    const m0 = s0.moved.get(name).tip.clone().sub(r0.tip);
    const big = Math.max(m1.length(), m0.length());
    const entry = { name, deg: deg(r1.dir, r0.dir), cos: null, ratio: big > 1e-3 ? Math.min(m1.length(), m0.length()) / big : 1 };
    if (m1.length() > 1e-3 && m0.length() > 1e-3) entry.cos = m1.clone().normalize().dot(m0.clone().normalize());
    const bad =
      !Number.isFinite(entry.deg) ||
      entry.deg >= LIMITS.restDeg ||
      (entry.cos !== null && entry.cos <= LIMITS.motionCos) ||
      entry.ratio < LIMITS.motionRatio;
    if (bad && declared.has(name)) declaredDiffs.push(entry);
    else kept.push(entry);
  }
  for (const name of missing) failures.push(`VRM0 に揺れ骨がない: ${name}`);
  for (const e of kept) if (e.ratio < LIMITS.motionRatio) failures.push(`揺れの大きさが違う: ${e.name}（小さい方/大きい方 = ${e.ratio.toFixed(2)}）`);
  const rest = [...kept].sort((a, b) => (Number.isFinite(b.deg) ? b.deg : 999) - (Number.isFinite(a.deg) ? a.deg : 999));
  const motion = kept.filter((e) => e.cos !== null).sort((a, b) => a.cos - b.cos);
  details.springs = {
    joints_vrm1: s1.joints.size,
    joints_vrm0: s0.joints.size,
    compared: kept.length + declaredDiffs.length,
    rest_worst: rest.slice(0, 8).map(({ name, deg }) => ({ name, deg })),
    motion_worst: motion.slice(0, 8).map(({ name, cos }) => ({ name, cos })),
    declared_differences: declaredDiffs,
  };
  for (const r of rest) {
    if (!Number.isFinite(r.deg)) failures.push(`揺れ骨の向きを計算できません: ${r.name}`);
    else if (r.deg >= LIMITS.restDeg) failures.push(`静止後の向きが違う: ${r.name} ${r.deg.toFixed(1)}°`);
  }
  for (const m of motion) if (m.cos <= LIMITS.motionCos) failures.push(`揺れの向きが違う: ${m.name} cos=${m.cos.toFixed(2)}`);
  if (!details.springs.compared && s1.joints.size) failures.push('揺れ骨を1つも突き合わせられませんでした');
}

// ---- 表情 ----
const VRM0_PRESET_NAMES = ['Joy', 'Angry', 'Sorrow', 'Fun', 'Surprised', 'A', 'I', 'U', 'E', 'O', 'Blink', 'Blink_L', 'Blink_R', 'LookUp', 'LookDown', 'LookLeft', 'LookRight', 'Neutral'];

function uniqueName(name, used) {
  let candidate = name;
  for (let n = 2; used.has(candidate); n++) candidate = `${name}_${n}`;
  used.add(candidate);
  return candidate;
}

function expressionNameMap(v1) {
  const used = new Set(VRM0_PRESET_NAMES);
  const map = new Map();
  for (const expr of v1.expressionManager.expressions) {
    const name = expr.expressionName;
    if (v1.expressionManager.presetExpressionMap[name]) map.set(name, name === 'surprised' ? 'Surprised' : name);
  }
  for (const name of Object.keys(v1.expressionManager.customExpressionMap)) map.set(name, uniqueName(name, used));
  return map;
}

function morphState(vrm) {
  const state = {};
  vrm.scene.traverse((obj) => {
    if (!obj.morphTargetInfluences || !obj.morphTargetDictionary) return;
    for (const [key, index] of Object.entries(obj.morphTargetDictionary)) {
      const value = obj.morphTargetInfluences[index];
      if (Math.abs(value) > 1e-6) state[`${obj.name}/${key}`] = Math.max(state[`${obj.name}/${key}`] ?? 0, value);
    }
  });
  return state;
}

function withExpression(vrm, name) {
  const manager = vrm.expressionManager;
  for (const expr of manager.expressions) manager.setValue(expr.expressionName, 0);
  manager.update();
  if (name) manager.setValue(name, 1);
  manager.update();
  return morphState(vrm);
}

function compareExpressions(v1, v0, failures, details) {
  const map = expressionNameMap(v1);
  const checked = [];
  for (const [n1, n0] of map) {
    if (!v0.expressionManager.getExpression(n0)) {
      failures.push(`VRM0 に表情がありません: ${n1} → ${n0}`);
      continue;
    }
    const a = withExpression(v1, n1);
    const b = withExpression(v0, n0);
    let worst = 0;
    for (const key of new Set([...Object.keys(a), ...Object.keys(b)])) worst = Math.max(worst, Math.abs((a[key] ?? 0) - (b[key] ?? 0)));
    checked.push({ vrm1: n1, vrm0: n0, morphs: Object.keys(a).length, worst });
    if (worst >= LIMITS.morph) failures.push(`表情のシェイプキーが違う: ${n1} → ${n0}（差 ${worst.toFixed(4)}）`);
  }
  withExpression(v1, null);
  withExpression(v0, null);
  details.expressions = { compared: checked.length, nonzero: checked.filter((c) => c.morphs).length, worst: checked.sort((a, b) => b.worst - a.worst).slice(0, 5) };
}

// ---- 視線の位置 ----
function compareLookAt(v1, v0, failures, details) {
  const point = (vrm) => characterFrame(vrm).point(vrm.lookAt.getLookAtWorldPosition(new THREE.Vector3()));
  const p1 = point(v1);
  const p0 = point(v0);
  const mm = p1.distanceTo(p0) * 1000;
  details.look_at = { vrm1: p1.toArray(), vrm0: p0.toArray(), diff_mm: mm };
  if (mm >= LIMITS.lookAtMm) failures.push(`視線の位置が違う: ${mm.toFixed(2)}mm（VRM1 ${p1.toArray().map((v) => v.toFixed(4))} / VRM0 ${p0.toArray().map((v) => v.toFixed(4))}）`);
}

// ---- 実行 ----
const args = process.argv.slice(2);
const takeOption = (flag) => {
  const i = args.indexOf(flag);
  return i >= 0 ? args.splice(i, 2)[1] : null;
};
const jsonOut = takeOption('--json');
const reportPath = takeOption('--report');
const [vrm1Path, vrm0Path] = args;
if (!vrm1Path || !vrm0Path) {
  console.error('使い方: node verify/compare_three_vrm.mjs <vrm1> <vrm0> [--json out.json]');
  process.exit(2);
}

const l1 = await loadVrm(vrm1Path);
const l0 = await loadVrm(vrm0Path);
const failures = [];
const details = { vrm1: vrm1Path, vrm0: vrm0Path, report: reportPath, meta_versions: [l1.vrm.meta.metaVersion, l0.vrm.meta.metaVersion] };
compareLookAt(l1.vrm, l0.vrm, failures, details);
compareExpressions(l1.vrm, l0.vrm, failures, details);
compareSprings(l1, l0, declaredJoints(l1.json, reportPath), failures, details);
details.failures = failures;

if (jsonOut) await fs.writeFile(jsonOut, JSON.stringify(details, null, 2), 'utf8');
console.log(JSON.stringify(details, null, 2));
console.log(failures.length ? `FAIL: ${failures.length} 件` : 'PASS');
process.exit(failures.length ? 1 : 0);
