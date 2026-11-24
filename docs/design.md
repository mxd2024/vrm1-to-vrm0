# VRM1 → VRM0 自動変換アドオン 設計書

- 作成日: 2026-11-24
- 状態: 設計（実装前・承認待ち）
- 置き場所: `D:\work\vrm1-to-vrm0\`（この文書は `docs\design.md`）

## 1. 目的と背景

制作工程で書き出した VRM 1.0 のアバターを、VRM 0.x しか前提にしていない利用先でも使えるように、Blender 上で VRM 0.x へ自動変換する。

- 最初の対象: 作者の手元のアバター 1 体（VRM 1.0。人型骨 52、表情 36、揺れもの 19 本）
- 利用先: three.js の Web アプリ（例: aituber-kit。three-vrm 3.4.4）、Unity（Cluster など）
- 揺れもの（SpringBone・コライダー）と表情（BlendShape）を含めて変換すること。手作業の再設定をなくすのが狙い。

過去に、1体分を手書きスクリプトで同期した実績がある。今回はそれを、どのモデルにも使える汎用アドオンにする。

## 2. ゴール／非ゴール／やってはいけないこと

### ゴール
1. 開いている VRM1 モデルの設定（骨割り当て・表情・揺れもの・コライダー・視線・一人称・利用条件）を、VRM Add-on の VRM0 設定欄へ写し替える操作。
2. VRM1 ファイルを指定すると「読み込み → 写し替え → VRM0 で書き出し → 変換レポート出力」を一度に行う操作。
3. Blender を画面なし（`blender -b`）で動かす実行口。AI エージェントや一括処理から呼べること。
4. 変換で失われる・近似される項目を、変換レポート（JSON と Markdown）に必ず書き出すこと。

### 非ゴール
- VRM0 → VRM1 の逆変換。
- 材質（MToon）の独自変換。VRM Add-on の VRM0 書き出しが MToon1 を MToon0 に自動変換する（`vrm0_exporter.py` の `write_mtoon1_downgraded_material`）ので、それに任せる。
- メッシュ・ウェイト・シェイプキーの編集。
- VRM Add-on 本体の改造。

### やってはいけないこと（技術的に動いても失敗とみなす）
- 元の `.vrm` や `.blend` を上書きすること。
- 利用条件（ライセンス）を推測で埋めること。VRM0 に対応欄がない項目は「要判断」としてレポートに挙げ、勝手な値を足さない。
- 異なる VRM1 コライダーグループを、VRM0 で1つのグループに統合すること（過去の事例で、スカート用の方向別の球を1グループにまとめた結果、静止 T ポーズでスカートがめくれ上がった）。
- 失われた項目をレポートに書かずに黙って捨てること。

## 3. 前提と制約

- Blender 5.2 以降（実機: `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`、5.2.3 LTS）。
- VRM Add-on for Blender（拡張機能 `bl_ext.user_default.vrm`、版 4.4.0）が有効であること。`blender_org` 側に 3.20.0 も入っているが無効。
  - 本アドオンは VRM Add-on の設定欄（PropertyGroup）に直接読み書きする。起動時に Add-on の有無と版を確認し、未導入なら操作を無効にして理由を表示する。動作確認済みの版（4.4.0）と違う版なら警告だけ出して続行する。
- 本アドオン自体も Blender 拡張機能の形（`blender_manifest.toml`）で作る。
- 実在の設定欄（実機の RNA から確認済み）:
  - `armature.data.vrm_addon_extension` の下に `spec_version`（`"1.0"` / `"0.0"`）、`vrm0`、`vrm1`、`spring_bone1`、`node_constraint1`
  - `vrm0.humanoid.human_bones[]`（`bone`, `node.bone_name`）
  - `vrm0.blend_shape_master.blend_shape_groups[]`（`name`, `preset_name`, `binds[]{mesh.mesh_object_name, index(シェイプキー名), weight(0〜1)}`, `material_values[]{material, property_name, target_value[]}`, `is_binary`）
    - `preset_name` の選択肢: `unknown, neutral, a, i, u, e, o, blink, joy, angry, sorrow, fun, lookup, lookdown, lookleft, lookright, blink_l, blink_r`
  - `vrm0.secondary_animation.bone_groups[]`（`comment, stiffiness, gravity_power, gravity_dir, drag_force, center, hit_radius, bones[], collider_groups[]`）
  - `vrm0.secondary_animation.collider_groups[]`（`node.bone_name`, `colliders[]{bpy_object}`, `uuid`）。VRM0 のコライダーは「骨を親にした Empty オブジェクト」で、半径は `empty_display_size` × スケール。
  - `vrm0.first_person`（`first_person_bone`, `first_person_bone_offset`, `mesh_annotations[]{mesh, first_person_flag}`, `look_at_type_name`, `look_at_horizontal_inner/outer`, `look_at_vertical_down/up`{`curve`(8値), `x_range`, `y_range`}）
  - `vrm0.meta`（`title, version, author, contact_information, reference, allowed_user_name, violent_ussage_name, sexual_ussage_name, commercial_ussage_name, other_permission_url, license_name, other_license_url, texture`）
  - `spring_bone1.springs[]{vrm_name, joints[]{node.bone_name, hit_radius, stiffness, gravity_power, gravity_dir, drag_force}, collider_groups[], center}`、`spring_bone1.colliders[]{node.bone_name, shape.sphere/capsule{offset, radius, tail}, shape_type, extensions.vrmc_spring_bone_extended_collider}`
- 表情の重みの 0〜100 への換算（`vrm0_exporter.py:603`）と、コライダー Empty のワールド位置から VRM0 の値への変換（同 `:700-721`）は、VRM Add-on の書き出し側が行う。本アドオンはそれらを Blender 上の値（ワールド座標・0〜1）で書く。
- **ただし、向きを表す値は VRM0 と VRM1 で Blender 上の持ち方が違うので、そのまま写してはいけない**（§6.3・§6.5）。
  - 重力の向き: VRM1 の関節は glTF 値 (x,y,z) を Blender 上で (x,-z,y) として持つ（`vrm1_importer.py:1681-1685`）。VRM0 の bone group は VRM0 の値 (x,y,z) を (x,z,y) として持つ（`vrm0_importer.py:1287-1288`、`vrm0_exporter.py:726-737`）。
  - 視線の位置: VRM1 の `offset_from_head_bone` は glTF の軸（Y が上）のまま持つ（`vrm1_exporter.py:559`）。VRM0 の `first_person_bone_offset` は (x,z,y) で持ち、書き出し時に y と z を入れ替える（`vrm0_exporter.py:852-858`）。
  - VRM0 と VRM1 ではモデルの正面の向き（glTF の ±Z）も違う。左右・前後の符号は、「元と同じ向きの値が、VRM0 の利用先（three-vrm）で同じ向きとして扱われる」ことを、往復テストで確かめて決める（§9）。

## 4. 作り方の案（検討結果）

| 案 | 中身 | 長所 | 短所 |
|---|---|---|---|
| **A（採用）** | 公式 VRM Add-on の上に「VRM1 設定 → VRM0 設定の写し替え」を足し、書き出しは Add-on に任せる | 材質・座標軸・重みの換算を実績ある Add-on に任せられる。Blender の画面でも画面なしでも使える | Add-on の内部の設定欄名に依存する。大きな更新で直しが要ることがある（版確認で検知） |
| B | Blender を使わず、VRM ファイルの中身を直接書き換える変換ツール | Blender 不要 | 前後の向きの反転・MToon 変換を全部自前で書き直すことになり、ずれやすい。「Blender アドオン」という依頼から外れる |
| C | three.js 側の制作ツール（Node／three-vrm）に変換を組み込む | three.js での確認環境に近い | Blender から使えず、Unity 向けの確認も別に要る |

ユーザーが A を選んだ。

## 5. 全体構成

```
D:\work\vrm1-to-vrm0\
  docs\design.md            この文書
  vrm1_to_vrm0\             Blender 拡張機能本体（zip にして導入）
    blender_manifest.toml
    __init__.py             登録・Add-on 版確認
    mapping.py              対応表（bpy に依存しない純 Python。単体テスト可能）
    convert.py              写し替え本体（bpy）
    colliders.py            VRM0 用コライダー Empty の生成・掃除
    report.py               変換レポート（JSON／Markdown）
    ops.py / ui.py          操作とサイドパネル
  cli\convert_vrm.py        画面なし実行口
  tests\                    mapping の単体テスト、Blender 上の結合テスト
  verify\                   three-vrm による動作確認スクリプト
```

### 操作
1. **「VRM0 設定へ写す」**: 選択中のアーマチュアについて、VRM1 設定を VRM0 設定へ写す。VRM1 側は一切変更しない。
2. **「VRM1 → VRM0 に変換して書き出す」**: 入力 VRM1 ファイルと出力先を指定。新しい空のシーン（または新規ファイル）に読み込み → 写し替え → `spec_version` を `"0.0"` にして VRM Add-on で書き出し → レポート出力。
   - 出力先の既定は入力と同じフォルダの `<元の名前>_vrm0.vrm`。同名ファイルがあれば上書きせず止める（上書きはオプション指定時のみ）。
   - 元の VRM と、ユーザーが開いている `.blend` には触れない。**メモリ上でも触れない**ため、画面から実行した場合も、別の Blender を画面なしで起動して下の「画面なし実行口」と同じ経路で処理する。開いているファイルにオブジェクトや画像が増えることはない。終わったら結果（成功／失敗・要判断の件数・レポートのパス）を画面に出す。

### 画面なし実行口
```
blender -b --python cli\convert_vrm.py -- <入力.vrm> [<出力.vrm>] [--overwrite]
```
- `--factory-startup` は付けない（付けるとユーザーの拡張機能＝VRM Add-on が読まれない）。
- 終了コード: 0 = 成功（要判断の項目があっても成功）、1 = 変換失敗、2 = 前提不足（Add-on なし等）。
- 標準出力の最後にレポート JSON のパスを1行で出す（AI や一括処理が拾えるように）。

### 再実行への強さ
- 写し替えは毎回 VRM0 設定欄を空にしてから書く（何度実行しても同じ結果）。
- 本アドオンが作るコライダー Empty は専用コレクション `VRM0_Colliders` に入れ、名前に接頭辞 `VRM0_COL_` を付ける。再実行時はこのコレクションの中身だけ消して作り直す。ほかのオブジェクトには触れない。

## 6. 変換規則

### 6.1 骨割り当て（humanoid）
- VRM1 の人型骨を、VRM0 の同じ骨に割り当てる（名前の形式だけ変換: `left_upper_arm` → `leftUpperArm` など）。
- **親指は1段ずらす**:
  - VRM1 `thumbMetacarpal` → VRM0 `thumbProximal`
  - VRM1 `thumbProximal` → VRM0 `thumbIntermediate`
  - VRM1 `thumbDistal` → VRM0 `thumbDistal`
- 目・顎など、VRM1 で未割り当ての骨は VRM0 でも未割り当てのまま。
- `use_default_values` などの VRM0 だけにある項目は、Add-on の既定値のまま。

### 6.2 表情（Expression → BlendShapeGroup）
決まった名前（プリセット）の対応:

| VRM1 | VRM0 preset_name | VRM0 name |
|---|---|---|
| happy | joy | Joy |
| angry | angry | Angry |
| sad | sorrow | Sorrow |
| relaxed | fun | Fun |
| surprised | unknown（VRM0 に該当なし） | Surprised |
| neutral | neutral | Neutral |
| aa / ih / ou / ee / oh | a / i / u / e / o | A / I / U / E / O |
| blink / blinkLeft / blinkRight | blink / blink_l / blink_r | Blink / Blink_L / Blink_R |
| lookUp / lookDown / lookLeft / lookRight | lookup / lookdown / lookleft / lookright | LookUp ほか |

- 独自表情（custom）は `preset_name = unknown`、`name` は VRM1 の名前をそのまま使う。
- VRM1 で中身（バインド）が空のプリセットも、グループとしては作る（空のまま）。
- 名前が重なった場合（例: 独自表情に `Surprised` がある）は、後から来たものに `_2` を付けてレポートに書く。
- **シェイプキーのバインド**: メッシュ名とシェイプキー名をそのまま写す。重みは 0〜1 のまま（書き出し時に Add-on が 0〜100 に換算）。
- **材質色のバインド**: VRM1 の種類 → VRM0 の材質プロパティ名
  - `color` → `_Color`、`shadeColor` → `_ShadeColor`、`emissionColor` → `_EmissionColor`、`rimColor` → `_RimColor`、`outlineColor` → `_OutlineColor`
  - **色空間を合わせる**: Add-on は材質そのものの色を書き出すとき linear → sRGB に変換し、発光色には発光の強さも掛ける（`vrm0_exporter.py:988,1018,1090,1130,1146`）。一方、表情の `material_values` は無変換で出る（同 `:606-622`）。表情の色を材質と同じ色空間・同じ強さにするため、Add-on が材質の同じ項目に行っているのと同じ変換を、写すときに値へかける。
  - `matcapColor` は VRM0 に対応がないので落とし、レポートに書く。
- **テクスチャ位置のバインド**: `_MainTex_ST` に写す。上下（オフセット Y）の扱いは VRM0 と VRM1 で違う。Add-on のプレビュー処理（`editor/vrm0/property_group.py:997-1026`、`1 - offset_v - scale_v` の式）が VRM0 の値を VRM1 相当に直しているので、その逆の式で写す。
- `is_binary` はそのまま写す。
- **抑制設定（overrideBlink / overrideLookAt / overrideMouth）**: VRM0 に項目がないので落とす。`none` 以外が付いていた表情はすべてレポートに書く（「笑顔とまばたきが重なる可能性あり」など、利用先で起きることを添える）。

### 6.3 揺れもの（SpringBone → secondaryAnimation）
- VRM1 の spring 1本 → VRM0 の bone group 1つ（`comment` に spring 名）。
  - `bones` には最初の関節（根元）の骨を1つ入れる。
  - **値は換算せず 1:1 で写す**（stiffness → `stiffiness`、`gravity_power`、`drag_force`、`hit_radius`）。three-vrm も UniVRM も VRM0 と VRM1 で同じ揺れの計算式を使っているため。過去の手書きスクリプトは値を倍率で変えていたが、あれは1体分の見た目の手直しで、汎用の変換規則にはしない。VRM0 の画面上の目安（stiffness 4 まで等）を超えていても、そのまま写す。
  - `gravity_dir` は §3 のとおり向きを直して写す。
  - 1本の spring の中で関節ごとに値が違う場合: VRM0 は1グループに1つの値しか持てない。**分割はせず、根元の関節の値を使い**、関節ごとの元の値をレポートに `lossy` として書く（分割すると、分けた側の根元が元のグループの子孫になり、その下の骨が2回計算されてしまうため）。
  - **入れ子の spring**（根元が、別の spring の根元より下にある）: VRM0 では親側のグループがすでにその骨を揺らすので、bone group を作らずに飛ばし、レポートに `lossy` として書く（過去スクリプトと同じ扱い。2回計算を避ける）。
  - `center` は写す。
- **VRM0 は根元より下の骨をすべて揺らす**。VRM1 で関節に含めていない枝（子の骨）が根元より下にある場合、VRM0 では余計に揺れる。これを検出してレポートに書く（自動で直すことはしない）。
- VRM1 の最後の関節は「位置を決めるだけ」の骨。VRM0 では末端の骨にも仮想の先端が付いて揺れるが、末端が変形に使われない骨なら見た目に影響しないので、変形に使われている末端骨だけ注意としてレポートに書く。

### 6.4 コライダー
- VRM0 のコライダーグループは「1つの骨に付いた球の集まり」。VRM1 のコライダーグループは複数の骨にまたがれる。
  - VRM1 のグループ1つを、骨ごとに VRM0 のグループへ分ける。
  - **異なる VRM1 グループのコライダーは、同じ骨に付いていても VRM0 で1つのグループにまとめない**（1対1の系統を保つ）。
  - bone group が参照するのは、その spring が参照していた VRM1 グループから分かれた VRM0 グループだけ。
- 球: 骨を親にした Empty（球表示）を、VRM1 と同じワールド位置に置き、半径を合わせる。
- カプセル: 中心線（offset → tail）に沿って球を並べる。球の間隔は半径以下（隙間で素通りしないため）、両端には必ず球を置く。何個の球に分けたかをレポートに書く。
- 拡張コライダー（内側の球・内側のカプセル・平面。`vrmc_spring_bone_extended_collider`）は VRM0 で表せない。普通の球・カプセルの代わりの形（fallback）が設定されていればそれを使い、なければ落としてレポートに書く。

### 6.5 視線（lookAt）と一人称（firstPerson）
- `type`: `bone` → `Bone`、`expression` → `BlendShape`。
- 範囲の対応（4方向とも同じ規則）: `x_range` = `input_max_value`、`y_range` = `output_scale`、`curve` は直線 `[0,0,0,1, 1,1,1,0]`。
- 値が不自然なものは写したうえで警告（例: 表情方式なのに `output_scale` が 1 を超える。今回のファイルは 10）。直すかどうかは人か AI が判断する。
- `offsetFromHeadBone` → `first_person_bone_offset`（§3 のとおり軸を直す。今回のファイルの「上に 3.5cm」が VRM0 で「前に 3.5cm」にならないこと）、`first_person_bone` = head に割り当てた骨。
- 一人称のメッシュ設定: `auto/both/thirdPersonOnly/firstPersonOnly` → `Auto/Both/ThirdPersonOnly/FirstPersonOnly`。

### 6.6 利用条件（meta）
機械的に写せるもの:

| VRM1 | VRM0 |
|---|---|
| name | title |
| version | version |
| authors（複数） | author（`, ` で連結） |
| contactInformation | contact_information |
| references（複数） | reference（`, ` で連結） |
| avatarPermission: onlyAuthor / onlySeparatelyLicensedPerson / everyone | allowed_user_name: OnlyAuthor / ExplicitlyLicensedPerson / Everyone |
| allowExcessivelyViolentUsage | violent_ussage_name（Allow / Disallow） |
| allowExcessivelySexualUsage | sexual_ussage_name（Allow / Disallow） |
| commercialUsage: personalNonProfit / personalProfit / corporation | commercial_ussage_name: Disallow / Allow / Allow |
| thumbnailImage | texture |

- `license_name` は `Other`、`other_license_url` には `https://vrm.dev/licenses/1.0/` を入れる（VRM1 の利用条件は VRM 1.0 ライセンス文書に従っているため）。Add-on は VRM1 の `licenseUrl` を保持せず（`editor/vrm1/property_group.py:1985-1987` でコメントアウト）、VRM1 書き出しでもこの固定値を出している（`vrm1_exporter.py:464`）ので、同じ固定値を使う。
- 対応欄がないもの（creditNotation、modification、allowRedistribution、allowPoliticalOrReligiousUsage、allowAntisocialOrHateUsage、copyrightInformation、thirdPartyLicenses、otherLicenseUrl）は、値を勝手に足さず、すべて「要判断」としてレポートに書く。
- commercialUsage が personalProfit / corporation の場合は、VRM0 では「個人か法人か」が区別できなくなることもレポートに書く。

### 6.7 その他
- ノードの拘束（`node_constraint1`）は VRM0 で表せない。あればレポートに書くだけ（焼き込みはしない）。
- 材質は VRM Add-on の自動変換に任せる。`KHR_materials_emissive_strength` など VRM0 で失われるものは、書き出した後のファイルを見て分かる範囲でレポートに書く。

## 7. 変換レポート

出力 VRM と同じ場所に `<出力名>.report.json` と `<出力名>.report.md` を作る。

- `summary`: 入出力パス、Add-on の版、各項目の件数（VRM1 側 → VRM0 側）。
- `items[]`: 1件ずつ `{ "section", "kind", "target", "message", "detail" }`。`kind` は次の3種類:
  - `info`: 規則どおりの変換（例: カプセルを球5つに分けた）
  - `lossy`: 失われた・近似した（例: 抑制設定が消えた）
  - `needs_decision`: 人か AI が決めるべきこと（例: 利用条件の対応欄なし、視線の値が不自然）
- Markdown 版は人が読む用。`needs_decision` を先頭にまとめる。

## 8. AI との連携

**変換そのものに AI は必須ではない。** すべて決まった規則で書ける。

AI（BlenderMCP 経由の Claude など）を使う場面は次の2つに限り、どちらも任意:
1. レポートの `needs_decision` を読み、利用先に合わせて値を決め、VRM0 設定欄を直して書き出し直す。
2. 確認手順（§9）の画像・数値を見て、揺れや表情の見た目に問題がないか判断する。

そのため、AI が扱いやすいように次を守る:
- 画面なし実行口とレポート JSON は、決まった形で出す（§5・§7）。
- 写し替えの関数は Blender の Python から直接呼べるようにする（`vrm1_to_vrm0.convert.convert_armature(armature) -> Report`）。

## 9. 確認方法

1. **読み直しの比較（自動）**: 出力した VRM0 を VRM Add-on で読み直し、元の VRM1 と比べる。
   - 人型骨の数、表情の数と名前、各表情のバインド数、揺れものの骨の総数、コライダーの球の数（カプセル分割後）、利用条件の写した項目。
2. **向きの往復テスト（自動）**: 重力の向きを前・横・下に設定した小さな VRM1 テストモデルと、視線の位置を上・横にずらしたテストモデルを用意し、変換後の VRM0 を three-vrm で読み、同じ向きになっていることを確かめる（§3 の符号を決めるためのテスト）。
3. **three-vrm での動作確認（自動）**: Node で three-vrm を使い、出力を読み込む。過去の `verify_vrm0_runtime.mjs` と同じ考え方で、
   - 読み込みエラーがないこと
   - 静止 T ポーズで数秒進めても揺れ骨が大きく動かないこと（スカートがめくれない）
   - 頭や腰を動かしたときに揺れ骨が動くこと
   - 各表情を 1.0 にしたときにシェイプキーが動くこと
4. **aituber-kit での見た目確認**: aituber-kit に出力を読み込ませ、表情と揺れを画面で確認する。
5. **Unity／Cluster での確認**: ユーザーにお願いする。

最初の対象ファイルで期待する値（元の VRM1 から）:
- 人型骨 52
- 表情: プリセット 18（うち surprised は独自扱い）+ 独自 18 = 36 グループ
- 揺れもの 19 本（全 spring で関節の値が均一なので bone group も 19）
- コライダー: 球 10 + カプセル 2（球に分割）、VRM1 のグループ 10
- レポートに出るはずの項目: 抑制設定の消失（angry/happy/relaxed/sad/surprised と独自表情の多数）、視線 `output_scale` 10 の警告、利用条件の対応欄なし（creditNotation・modification・allowRedistribution など）

## 10. 設計時に Claude が決めたこと（ユーザー確認待ち）

- 揺れの値は換算せず 1:1 で写す（§6.3）。
- 1本の spring の中で値が違うときは分割せず、根元の値を使う。入れ子の spring は飛ばす。どちらもレポートに書く（§6.3）。
- 画面から変換して書き出す操作も、別の Blender を画面なしで起動して処理する（§5）。
- 利用条件の `other_license_url` は VRM 1.0 ライセンスの固定 URL にする（§6.6）。

## 11. 作る人に任せること

- サイドパネルの細かい見た目と配置。
- カプセルを球に分ける具体的な間隔の式（§6.4 の条件を満たす範囲で）。
- テストの細かい構成。
- 名前が重なったときの付け方の細部（§6.2 の方針の範囲で）。

## 12. 実装で分かった訂正（2026-11-24 追記）

- §3・§6.5 の視線の位置: VRM1 の `offsetFromHeadBone` は「glTF の軸のまま」ではなく、**頭ノードの向き**での値。頭ノードが回転しているモデル（最初の対象は Y 軸まわりに約 180°）があるため、頭の骨の向きで読んでから VRM0 の値にする。
- §3 の重力の向きの符号: VRM0 の値は UniVRM（Unity の座標）の決まりで書く。three-vrm は VRM0 の重力の左右を逆に扱うため、左右向きの重力だけは three.js と Unity で両立しない。該当する spring はレポートに `needs_decision` を出す（§9-2 の往復テストで確認）。
- §5 の画面なし実行口は `cli\convert_vrm.py` ではなく `vrm1_to_vrm0\cli.py`（拡張機能の中。画面の操作も同じものを呼ぶ）。
