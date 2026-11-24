"""VRM1 → VRM0 の対応表。bpy に依存しない純関数だけを置く。"""
import math

from .report import ReportItem

_THUMB_SHIFT = {
    "thumb_metacarpal": "ThumbProximal",
    "thumb_proximal": "ThumbIntermediate",
    "thumb_distal": "ThumbDistal",
}


def vrm0_human_bone_name(vrm1_snake):
    """VRM1 の人型骨名（Add-on の snake 名）→ VRM0 の人型骨名。親指は1段ずらす。"""
    for side in ("left", "right"):
        for suffix, vrm0 in _THUMB_SHIFT.items():
            if vrm1_snake == f"{side}_{suffix}":
                return side + vrm0
    parts = vrm1_snake.split("_")
    if not parts or not all(parts):
        return None
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


# VRM1 preset（Add-on の snake 名）→ (VRM0 preset_name, VRM0 name)。順序は書き出し順。
EXPRESSION_PRESETS = {
    "happy": ("joy", "Joy"),
    "angry": ("angry", "Angry"),
    "sad": ("sorrow", "Sorrow"),
    "relaxed": ("fun", "Fun"),
    "surprised": ("unknown", "Surprised"),
    "aa": ("a", "A"),
    "ih": ("i", "I"),
    "ou": ("u", "U"),
    "ee": ("e", "E"),
    "oh": ("o", "O"),
    "blink": ("blink", "Blink"),
    "blink_left": ("blink_l", "Blink_L"),
    "blink_right": ("blink_r", "Blink_R"),
    "look_up": ("lookup", "LookUp"),
    "look_down": ("lookdown", "LookDown"),
    "look_left": ("lookleft", "LookLeft"),
    "look_right": ("lookright", "LookRight"),
    "neutral": ("neutral", "Neutral"),
}


def unique_name(name, used):
    """used と重ならない名前を返し、used に足す。重なれば _2, _3… を付ける。"""
    candidate = name
    n = 2
    while candidate in used:
        candidate = f"{name}_{n}"
        n += 1
    used.add(candidate)
    return candidate


# Add-on の material_color_binds[].type → VRM0 の材質プロパティ名
MATERIAL_COLOR_PROPERTY = {
    "color": "_Color",
    "shadeColor": "_ShadeColor",
    "emissionColor": "_EmissionColor",
    "rimColor": "_RimColor",
    "outlineColor": "_OutlineColor",
    "matcapColor": None,
}


def texture_transform_to_main_tex_st(scale, offset):
    """VRM1 のテクスチャ位置（KHR_texture_transform）→ VRM0 の _MainTex_ST。"""
    sx, sy = scale
    ox, oy = offset
    return [sx, sy, ox, 1 - oy - sy]


def linear_to_srgb(c):
    """Add-on（common/convert.py の linear_to_srgb）と同じ式。"""
    return math.pow(c, 1.0 / 2.2)


def look_at_type(vrm1):
    return {"bone": "Bone", "expression": "BlendShape"}[vrm1]


def look_at_range(input_max, output_scale):
    return {"curve": [0, 0, 0, 1, 1, 1, 1, 0], "x_range": input_max, "y_range": output_scale}


def first_person_flag(vrm1):
    return {
        "auto": "Auto",
        "both": "Both",
        "thirdPersonOnly": "ThirdPersonOnly",
        "firstPersonOnly": "FirstPersonOnly",
    }[vrm1]


def _blender_world_to_vrm0_storage(v):
    """Blender ワールドのベクトル → Add-on が持つ VRM0 の値。

    VRM0 の JSON は Unity の座標（正面 +Z、キャラクターの左 -X）で、Blender からは (-x, z, -y)。
    Add-on は VRM0 の重力の向き・視線の位置を JSON の (x, z, y) として持つので、合わせて (-x, -y, z)。
    three-vrm（aituber-kit と同じ版）と UniVRM の決まりで確かめた（重力の左右だけは three-vrm が逆に扱う）。
    """
    x, y, z = v
    return (-x, -y, z)


def vrm0_gravity_dir(vrm1_blender):
    """VRM1 関節の gravity_dir（Blender ワールドの向き）→ VRM0 bone group の gravity_dir（Add-on の値）。"""
    return _blender_world_to_vrm0_storage(vrm1_blender)


def vrm0_first_person_offset(offset_world):
    """頭から視線の位置までのベクトル（Blender ワールド）→ VRM0 の first_person_bone_offset（Add-on の値）。

    VRM0 の頭ノードは回転を持たないので、ワールドの向きのまま入れる。
    """
    return _blender_world_to_vrm0_storage(offset_world)


def capsule_spheres(head, tail, radius):
    """カプセルの中心線に、両端を含み間隔が radius 以下の最少個数で等間隔に球を並べる。"""
    length = math.dist(head, tail)
    if length <= 1e-9 or radius <= 0:
        return [tuple(head)]
    segments = max(1, math.ceil(length / radius - 1e-9))
    return [
        tuple(h + (t - h) * i / segments for h, t in zip(head, tail))
        for i in range(segments + 1)
    ]


VRM1_LICENSE_URL = "https://vrm.dev/licenses/1.0/"

_AVATAR_PERMISSION = {
    "onlyAuthor": "OnlyAuthor",
    "onlySeparatelyLicensedPerson": "ExplicitlyLicensedPerson",
    "everyone": "Everyone",
}

# VRM0 に対応欄がない VRM1 の欄
_NO_VRM0_FIELD = (
    "credit_notation",
    "modification",
    "allow_redistribution",
    "allow_political_or_religious_usage",
    "allow_antisocial_or_hate_usage",
    "copyright_information",
    "third_party_licenses",
    "other_license_url",
)


def _allow(flag):
    return "Allow" if flag else "Disallow"


def meta_to_vrm0(meta1):
    """VRM1 meta（Add-on の欄名の dict）→ (VRM0 meta の dict, ReportItem のリスト)。"""
    commercial = meta1.get("commercial_usage", "personalNonProfit")
    meta0 = {
        "title": meta1.get("vrm_name", ""),
        "version": meta1.get("version", ""),
        "author": ", ".join(meta1.get("authors", [])),
        "contact_information": meta1.get("contact_information", ""),
        "reference": ", ".join(meta1.get("references", [])),
        "allowed_user_name": _AVATAR_PERMISSION[meta1.get("avatar_permission", "onlyAuthor")],
        "violent_ussage_name": _allow(meta1.get("allow_excessively_violent_usage", False)),
        "sexual_ussage_name": _allow(meta1.get("allow_excessively_sexual_usage", False)),
        "commercial_ussage_name": "Disallow" if commercial == "personalNonProfit" else "Allow",
        "license_name": "Other",
        "other_license_url": VRM1_LICENSE_URL,
    }
    items = []
    for key in _NO_VRM0_FIELD:
        if key not in meta1:
            continue
        items.append(
            ReportItem(
                "meta",
                "needs_decision",
                key,
                f"VRM0 に対応する欄がありません（VRM1 の値: {meta1[key]!r}）。必要なら other_permission_url などで伝えるか判断してください。",
                {"vrm1_value": meta1[key]},
            )
        )
    if commercial in ("personalProfit", "corporation"):
        items.append(
            ReportItem(
                "meta",
                "lossy",
                "commercial_usage",
                f"VRM1 の {commercial} は VRM0 では Allow になり、個人か法人かの区別が失われます。",
                {"vrm1_value": commercial},
            )
        )
    return meta0, items
