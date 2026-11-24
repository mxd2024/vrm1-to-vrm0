# VRM1 → VRM0 変換アドオン（Blender 5.2 拡張機能）

VRM 1.0 のアバターを VRM 0.x に変換します。骨の割り当て・表情・揺れもの（SpringBone とコライダー）・視線・一人称・利用条件を、[VRM Add-on for Blender](https://vrm-addon-for-blender.info/) の VRM1 設定から VRM0 設定へ写し、書き出しは VRM Add-on に任せます。変換で失われるもの・人が決めるべきものは、必ずレポートに書き出します。

- 動作環境: Blender 5.2 以降、VRM Add-on for Blender 4.4.0（動作確認済み。ほかの版では警告を出して続行します）
- 設計: [docs/design.md](docs/design.md)
- ライセンス: GPL-3.0-or-later（[LICENSE](LICENSE)）

## 導入

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --command extension build --source-dir vrm1_to_vrm0 --output-dir dist
```

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --command extension install-file -r user_default -e dist\vrm1_to_vrm0-0.1.0.zip
```

`dist` フォルダは先に作っておきます。Blender の画面を開いたまま導入した場合は、Blender を再起動してください。

## 使い方（画面）

3D ビューのサイドバー（N キー）の「VRM」タブに「VRM1 → VRM0 変換」パネルが出ます。

1. **VRM0 設定へ写す** — 選択中のアーマチュアの VRM1 設定を VRM0 設定へ写します。VRM1 側は変えません。VRM のバージョンが 1.0 のモデルでだけ押せます（VRM0 のモデルの手作りの設定を消さないため）。結果はテキスト「VRM0_conversion_report.md」に入ります。VRM0 として書き出すには、VRM Add-on で VRM のバージョンを 0.x にして書き出してください。
2. **VRM1 → VRM0 に変換して書き出す** — 入力の VRM1 ファイルと出力先を指定します（出力が空なら `<入力>_vrm0.vrm`）。別の Blender を画面なしで起動して処理するので、開いているファイルには何も読み込まれません。同名の出力があると止まります（「同名ファイルを上書き」で上書き）。

## 使い方（画面なし・AI や一括処理から）

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --python-exit-code 1 --python vrm1_to_vrm0\cli.py -- "入力.vrm" ["出力.vrm"] [--overwrite]
```

- `--factory-startup` は付けないでください（VRM Add-on が読まれなくなります）。
- 終了コード: `0` 成功（要判断の項目があっても成功）／`1` 変換失敗（出力が既にある、を含む）／`2` 前提不足（入力がない、VRM1 でない、Add-on がない など）。
- 標準出力の最後の行は `REPORT: <レポート JSON のパス>` です。レポートを書かずに止まったときは `REPORT: ` だけで、直前の `ERROR: ` 行に理由が出ます。
- 導入済みの拡張機能の中の `cli.py`（`%APPDATA%\Blender Foundation\Blender\5.2\extensions\user_default\vrm1_to_vrm0\cli.py`）も同じように使えます。
- Blender の中の Python からは `vrm1_to_vrm0.convert.convert_armature(armature_object)` で写し替えだけを呼べます（戻り値はレポート）。

## レポートの読み方

出力と同じ場所に `<出力>.report.json`（機械用）と `<出力>.report.md`（人用）ができます。

- `summary`: 入出力パス、Add-on の版、件数（VRM1 側・VRM0 側）、`roundtrip`（書き出した VRM0 を読み直して、書き出し前の値と比べた結果）、`collider_group_map`（VRM1 コライダーグループ → 分けた VRM0 コライダーグループ）
- `items[]`: `{section, kind, target, message, detail}`。`kind` は3種類
  - `needs_decision` — 人か AI が決めること（利用条件の対応欄がない、視線の値が不自然、重力に左右の向きがある など）
  - `lossy` — 失われた・近似したもの（表情の抑制設定、関節ごとに違う揺れの値、VRM0 で出せない拡張 など）
  - `info` — 規則どおりの変換（カプセルを球 N 個に分けた など）

## AI に判断させるとき（任意）

変換そのものに AI は要りません。AI（BlenderMCP 経由の Claude など）に頼むのは次の2つだけです。

1. **要判断の項目を決める**: CLI を実行 → 最後の行のレポート JSON を読む → `needs_decision` ごとに利用先（three.js / Unity・Cluster など）に合わせて値を決める → 出力 VRM0 を VRM Add-on で読み込み、VRM0 設定欄を直して書き出し直す。利用条件は推測で埋めず、決めた根拠を残してください。
   - 出力 VRM0 は利用条件が `Other`（VRM 1.0 ライセンスの URL）なので、VRM Add-on で読み込むと利用条件の確認画面が出ます。画面では確認して読み込みます。画面なしの Blender で読み込むときは、環境変数 `BLENDER_VRM_AUTOMATIC_LICENSE_CONFIRMATION=true` を付けないと何も読み込まれません（元のモデルの利用条件を確かめてから付けてください）。
   - 直すより先に、元の VRM1 で直して変換し直すほうが簡単な項目も多いです（視線の値など）。
2. **見た目を確かめる**: 下の比較スクリプトの結果や、利用先での表示を見て、揺れや表情に問題がないか判断する。

## 確認方法

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe" -m unittest discover -s tests/unit -t . -v
```

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --python-exit-code 1 --python tests/blender/run.py -- "test_*"
```

テストは、その場で作るテスト用モデル（basic / springs / empty）で動きます。実際のアバターでの回帰テスト（骨・表情・揺れものの件数などを確かめるもの）は、環境変数 `VRM1TO0_SAMPLE_VRM` に VRM1 ファイルのパスを入れたときだけ動き、未設定なら飛ばします。件数は作者の手元のモデルに合わせてあるので、ほかのモデルでは合いません。

three-vrm（aituber-kit と同じ 3.4.4）で元の VRM1 と変換後の VRM0 を同じ条件で動かして比べる（Node.js 22 以降。先に three と three-vrm を `verify` に入れます）:

```powershell
npm install --prefix verify
```

```powershell
node verify\compare_three_vrm.mjs "元.vrm" "元_vrm0.vrm" --report "元_vrm0.vrm.report.json" --json out.json
```

視線の位置（差 1mm 未満）、各表情のシェイプキーの値（差 1e-3 未満）、静止 3 秒後の揺れ骨の向き（差 5° 未満）、体を揺らしたときの揺れの向き（cos > 0.9）を比べます。`--report` を渡すと、レポートが既に申告しているずれは `declared_differences` に分けて出し、失敗に数えません。three と three-vrm は `verify\node_modules` から読みます（環境変数 `THREE_VRM_FROM` で、それらが入った別のプロジェクトの `package.json` を指せます）。

## 変換の決まり（要点）

- 骨: 名前の形式だけ変換。親指は VRM1 の Metacarpal/Proximal/Distal → VRM0 の Proximal/Intermediate/Distal。
- 表情: プリセットは対応表どおり（happy→Joy、relaxed→Fun、surprised は VRM0 に無いので独自表情 Surprised）。材質色は Add-on が材質を書き出すときと同じ色の変換（linear→sRGB、発光は強さを掛ける）。テクスチャ位置は `_MainTex_ST`。抑制設定（overrideBlink など）は VRM0 に無いので失われます。
- 揺れもの: spring 1本 → bone group 1つ。値は 1:1。関節ごとに値が違えば根元の値を使い、入れ子の spring は作りません（どちらもレポートに書きます）。
- コライダー: VRM1 のグループを骨ごとに分けます。違う VRM1 グループのコライダーは同じ骨でもまとめません。カプセルは中心線に沿って半径以下の間隔で球を並べます。作った Empty はコレクション `VRM0_Colliders`、名前は `VRM0_COL_` で始まり、再実行時はそのアーマチュアに付いたものだけを作り直します（1つのファイルにほかのアバターがいても消しません）。
- 視線の位置: VRM1 の `offsetFromHeadBone` は頭の骨の向きで読みます（頭の骨が回転しているモデルがあるため）。
- 利用条件: 機械的に写せる欄だけ写し、`license_name = Other`、`other_license_url = https://vrm.dev/licenses/1.0/`。VRM0 に対応欄がない項目はすべて `needs_decision`。

## 既知の制限

- **重力に左右の向きがある揺れもの**: VRM0 の値は UniVRM（Unity・Cluster）の決まりで書きます。three-vrm（aituber-kit など）は VRM0 の重力の左右を逆に扱うため、three.js 側では左右が反対に揺れます。前後・上下は両方で一致します。該当する spring はレポートに `needs_decision` で出ます（多くのモデルは下向きだけなので影響しません）。
- 拡張コライダー（内側の球・カプセル、平面）は代わりの形（fallback）にして `lossy` を出します。テスト用モデルでは未確認です。
- ノードの拘束（VRMC_node_constraint）は VRM0 で表せないため書き出されません（`lossy`）。
- ほかのアドオン（blendkit など）が起動直後に落ちることがあり、画面なしの Blender がまれに異常終了します。画面の「変換して書き出す」は1回だけ自動でやり直します。CLI を直接使うときは、終了コードが 0/1/2 以外ならもう一度実行してください。
