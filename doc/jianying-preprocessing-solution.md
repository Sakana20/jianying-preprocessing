# 剪映工程预处理 Skill：样本研究与实现方案

## 文档状态

- 状态：方案研究完成，尚未实现代码
- 研究日期：2026-09-07
- 首版目标版本：剪映专业版 5.9.0，`draft_info.json.version = 360000`
- 研究方式：只读检查两个本地剪映工程、工程备份时间序列、媒体文件及现有 `jianying-editor` 能力

## 目标

前置 Skill 会准备好一个有效的剪映工程。本 Skill 对该工程进行预处理：

1. 将时间线视频连接到对应文件；若失败是权限问题，进行可审计的最小修复或引导原生授权。
2. 添加风险提示图，通常为透明 PNG。
3. 统一字幕的字体样式、行间距、缩放和位置。
4. 添加产品名高亮。
5. 添加利益点高亮。

首版应保留前置工程已有的轨道、片段 ID、素材 ID、时间范围和未知字段，不重新生成时间线。

## 参考工程

### 源工程

```text
/Users/sakana/Movies/JianyingPro/User Data/Projects/com.lveditor.draft/1
```

### 人工预处理后的工程

```text
/Users/sakana/Movies/JianyingPro/User Data/Projects/com.lveditor.draft/2
```

两个样本均为：

- 剪映专业版：5.9.0
- Draft version：360000
- 画布：720 × 1280，9:16
- 帧率：30 fps
- 工程时长：251166666 微秒
- 源工程：3 条轨道、127 个片段
- 处理后：4 条轨道、128 个片段

工程 2 是工程 1 的副本。`draft_info.json` 内部工程 ID 被保留，但 `draft_meta_info.json.draft_id`、工程名及目录元数据发生了复制相关变化。这类差异不是预处理规则。

## 样本结论总览

| 功能 | 样本中观察到的处理 | 实现含义 |
|---|---|---|
| 视频重连 | 10 个视频的绝对路径、素材主键、片段主键和时间线均未变化 | 不能仅凭 `path` 判断是否已连接 |
| 风险提示 | 新增 1 个 photo material、1 条 video track、1 个全片 segment 及辅助素材 | 不能只向 JSON 增加一个图片路径 |
| 字幕样式 | 116 条字幕统一字体、描边、行间距 | 需同时修改 text material 和 text segment |
| 字幕布局 | 116 条字幕统一缩放和位置 | 布局在 segment 的 `clip` 中，不在 text material 中 |
| 产品名高亮 | 10 处“淘宝闪购”变为黄色 | 需生成完整、连续的富文本 range |
| 利益点高亮 | 两个利益点使用不同视觉样式 | 利益点规则必须支持逐短语配置，而非一个全局颜色 |
| 换行 | 10 处利益点字幕由逗号改为换行 | 应作为显式规则，不能当作高亮的隐式副作用 |

## 剪映 5.9 工程关系模型

当前样本没有 `draft_content.json`，权威时间线文件为 `draft_info.json`。

视频与图片素材的主要关系链为：

```text
tracks[type=video].segments[].material_id
    -> materials.videos[].id
```

重要约束：

- 关联主键是 `materials.videos[].id`。
- `materials.videos[].material_id` 不是关系主键；人工重连后它可以为空。
- 图片同样存放在 `materials.videos`，但 `type = "photo"`。
- 因此不能把 `materials.videos[]` 的每一项都当作业务视频。
- `segment.extra_material_refs[]` 会指向 speed、canvas、sound channel、loudness、animation、vocal separation 等辅助素材。
- 每次保存后必须校验所有主引用和辅助引用闭合。

字幕关系链为：

```text
tracks[type=text].segments[].material_id
    -> materials.texts[].id
```

应从目标字幕轨引用的 material 集合开始处理，不能无条件修改 `materials.texts` 中的所有文字素材，因为真实工程可能同时包含标题、贴纸文字或其他文本轨。

## 视频重连研究

### 稳定关系

10 个业务视频均位于：

- Track ID：`98f6ccc4f54142bc92eeeed59f875146`
- Track name：`视频素材`
- Track type：`video`

特殊封面占位素材位于另一条轨道，文件为 `cover_track_placeholder_1frame.mp4`，只有一帧，不能误判为业务视频。

风险 PNG 在处理后也成为 `materials.videos[type=photo]`，同样必须排除。

### 人工重连前后的精确差异

工程 2 的备份时间序列可以将“视频重连”和后续字幕/风险图操作分开：

```text
重连前：2/.backup/20260907141229_3fc33415b0a074115af2729e1e847f60.load.bak
重连后：2/.backup/20260907141255_b5285f18d0d579d88f4d52c40e3b6daf.save.bak
```

这一阶段：

- Track 数仍为 3。
- Video material 数仍为 11。
- 10 个业务视频的 `path` 完全未变。
- `materials.videos[].id` 未变。
- Segment ID 及 `segment.material_id` 未变。
- 宽高、素材时长、`has_audio`、source/target timerange 均未变。

每个业务视频只有以下四个普通字段一致变化：

```text
category_name: "local" -> ""
is_copyright: false -> true
material_id: <与 id 相同> -> ""
material_name: <原文件名> -> ""
```

同时，每个业务 segment 的 `extra_material_refs` 最后两个 UUID 被刷新：

- 一个 `materials.loudnesses` ID
- 一个 `materials.vocal_separations` ID

去掉 ID 后，新旧辅助对象语义相同。更早的多次 load 备份也显示剪映会自行刷新这些 UUID。因此：

- 不要硬编码这些 UUID。
- 不要把 UUID 变化当作内容变更。
- 不要主动模仿 UUID churn。
- 上述四字段组合只能作为本次剪映 5.9 原生重连的观察特征，不能视为稳定跨版本协议。
- 不能通过手工清空这四个字段来“伪造重连成功”。

### 当前媒体状态

10 个媒体文件当前均满足：

- 文件存在且可读，mode 为 0644。
- 视频为 H.264、1080 × 1920、yuv420p。
- 包含 AAC 音频。
- ffprobe 可以正常解析。
- Draft 时长与 ffprobe 容器时长最多相差不到一帧。

因此源封面中的“媒体格式不支持”并非真实编码不兼容，更可能是当时的剪映沙盒访问权或原生导入状态问题。

### 推荐的媒体解析算法

前置 Skill 最好提供精确 manifest。推荐字段：

```json
{
  "material_id": "5836a9df30414e8b9edadd0cc4670394",
  "segment_id": "99f05267e8594309be7079866da00a31",
  "original_basename": "MCD25-001.mp4",
  "expected_path": "/absolute/path/MCD25-001.mp4",
  "size": 20050542,
  "duration_us": 15066666,
  "width": 1080,
  "height": 1920,
  "has_audio": true,
  "sha256": null
}
```

解析顺序：

1. 优先验证 manifest 的 `expected_path`。
2. 其次验证 Draft 内已有绝对路径。
3. 两者失败时，才扫描 job 显式提供的有限 `search_roots`。
4. 先按 basename、文件大小、宽高、音频存在性、时长容差一帧过滤。
5. 仍有多个候选时计算 hash。
6. 只在素材身份唯一时更新 `materials.videos[].path`。
7. 保留 material ID、segment ID、时间线和既有辅助引用。

需处理 macOS 的 Unicode NFC/NFD 文件名差异和卷大小写敏感性。外接盘场景最好由前置 manifest 提供 volume UUID 与卷内相对路径，不能只依赖 `/Volumes/<显示名称>`。

## 权限与沙盒边界

### 当前样本可以确认的事实

- 业务视频和父目录当前没有 POSIX 读权限故障。
- 视频文件目前带有 `VideoFusion-macOS` 写入的 `com.apple.quarantine` 和 `com.apple.provenance`。
- 这些标记在成功处理后仍然存在，所以删除 quarantine 不是本例的修复方式。
- 业务视频自身没有 `com.apple.macl`；部分父目录和工程目录带有该不透明标记。
- 命令行进程可读，不等于 bundle id `com.lemon.lvpro` 的剪映进程具有相同 TCC 权限。

### 权限分类

预检必须区分：

1. 文件不存在。
2. 外接卷未挂载。
3. 父目录不可 traverse。
4. 文件对当前 owner 不可读。
5. ACL 明确阻止访问。
6. macOS Files & Folders / Desktop / Removable Volumes TCC 授权不足。
7. 文件可读但剪映原生导入状态异常。

只在用户显式允许 `repair_permissions` 时，才可对精确目标进行最小 POSIX 修复：

- 文件仅增加 owner read：`u+r`
- 必要父目录仅增加 owner execute：`u+x`
- 记录修改前 mode，以便 rollback

禁止：

- `chmod -R`
- `chmod 777`
- 对整盘清理 ACL
- 写入或替换 TCC 数据库
- 复制、清除或伪造 `com.apple.macl`
- 把 symlink 当作绕过 TCC 的可靠方案

当 Codex 可读但剪映不可读时，推荐两条路径：

1. 通过剪映原生文件选择器执行一次重连/目录授权。
2. 经用户选择，将素材 APFS clone 或 copy 到剪映稳定可访问的 staging，例如目标工程下受控的 `Resources/local_media`，再更新路径。

复制策略必须显式配置，因为它影响磁盘空间和工程可移植性。

## 风险提示图研究

样本图片：

```text
/Volumes/Elements SE/陈鼎琦/饿了么整理/风险提示语排版/淘宝闪购星广提示语.png
```

图片属性：

- 720 × 1280
- RGBA，含透明通道
- 与画布尺寸完全一致
- 非透明内容约位于 `x=5..56, y=285..993`

处理后新增：

- 1 个 `materials.videos` 对象，`type = "photo"`
- 1 个 video track
- 1 个覆盖全片的 segment
- 1 个 speed
- 1 个 canvas
- 1 个空 `sticker_animation`
- 1 个 sound channel mapping
- 1 个 vocal separation

风险图 segment 的主要参数：

```json
{
  "target_timerange": {"start": 0, "duration": 251166666},
  "source_timerange": {"start": 0, "duration": 251166666},
  "clip": {
    "alpha": 1.0,
    "rotation": 0.0,
    "scale": {"x": 1.0, "y": 1.0},
    "transform": {"x": 0.0, "y": 0.0}
  },
  "track_render_index": 3,
  "render_index": 1,
  "visible": true
}
```

该轨道位于原字幕轨之上。图片 material 自身使用剪映静态图片的长 duration，而 segment 只引用工程实际时长。

### 风险图 sidecar

原生导入还更新了：

- `draft_meta_info.json`：新增本地 photo material 记录。
- `key_value.json`：新增 material 记录和 segment-to-material 记录。
- `draft_virtual_store.json`：新增本地素材父子关系。

这些文件使用多套不同 ID，不能假设它们与 `draft_info.json` material ID 相同。实现时应统一生成、记录映射并纳入同一事务。

首版对风险图建议默认要求：

- PNG/RGBA
- 与项目画布尺寸一致
- 从 0 覆盖到 Draft duration
- 只存在一条相同用途的风险图轨道

尺寸不匹配时默认阻止 apply，并要求 job 显式选择 `fit`、`fill` 或坐标变换，不能静默拉伸。

## 字幕样式研究

目标字幕轨：

- Track ID：`9eab756583e84826b47ec26351d3e8ee`
- Track name：`字幕`
- Track type：`text`
- Segment 数：116

### Text material 变化

116 个 `materials.texts` 全部发生：

```text
line_spacing: 0.02 -> 0.25
check_flag: 7 -> 15
text_color: "" -> 基础值 #ffffff
border_color: "" -> 基础值 #000000
background_color: "" -> #000000
font_resource_id: "" -> 6740439840254333443
font_path: 系统字体 -> 特黑体缓存文件
fonts: [] -> 1 个字体资源描述
```

字体资源：

```text
名称：特黑体
Resource ID：6740439840254333443
本机文件：特黑体-思源黑体1号.otf
```

字体缓存绝对目录包含机器相关 hash，Profile 不应只硬编码完整路径。运行时应按以下顺序解析：

1. Job 显式 `font_path`。
2. Profile 的 resource ID 和名称。
3. 剪映缓存目录中的文件名与可选文件 hash。
4. 无唯一结果时阻止 apply。

不要在未确认字体授权的情况下把字体文件直接打包进 Skill。

### Content 样式

基础字幕语义为：

- 字号：`content.styles[].size = 5`
- 字色：白色 `#FFFFFF`
- 描边：黑色 `#000000`
- 描边宽度：约 `0.08`
- 字体：特黑体 resource ID `6740439840254333443`
- `useLetterColor = true`

工程中的 `preset_id`、`text_preset_resource_id`、`preset_name`、`style_name` 仍为空。因此这里不是引用一个剪映动态预设，而是把样式实体化到每一个字幕 material。Skill 内应使用自己的版本化 Profile 表达这个预设。

### Segment 布局变化

116 个字幕 segment 全部发生：

```text
clip.scale.x: 1.0 -> 2.5
clip.scale.y: 1.0 -> 2.5
clip.transform.x: 0.0 -> 0.0
clip.transform.y: -0.8 -> -0.390625
```

字幕 segment 的 ID、material ID、起止时间、持续时间、render index 等均保持不变。

## 产品名与利益点高亮

### 样本产品名规则

10 条重复字幕中的“淘宝闪购”被高亮：

```text
原文：淘宝闪购有
range [0, 4)：淘宝闪购，黄色填充 #FFDE00，黑色描边
range [4, 5)：有，白色填充，黑色描边
```

“淘宝闪购”属于产品/活动词，是根据用户业务语义分类，不是 Draft 自带的语义标签。运行时必须由 job 或前置 Skill 提供产品名和别名。

### 样本利益点规则

10 条重复字幕从：

```text
最高25元无门槛红包，还可以叠加九折津贴卡
```

改为：

```text
最高25元无门槛红包
还可以叠加九折津贴卡
```

最终 range：

| Range | 文本 | 填充 | 描边 |
|---|---|---|---|
| `[0, 2)` | 最高 | 白色 | 黑色 |
| `[2, 10)` | 25元无门槛红包 | `#FFDE00` | 黑色 |
| `[10, 16)` | 换行 + 还可以叠加 | 白色 | 黑色 |
| `[16, 21)` | 九折津贴卡 | 白色 | `#FF1837` |

这证明利益点高亮必须支持每条规则分别配置 fill、stroke、size、bold 等属性。

### Range 生成要求

实现不能简单追加高亮 span。应生成覆盖全文的、连续且不重叠的样式分区：

```text
[基础范围] [高亮范围] [基础范围] ...
```

校验条件：

- 第一个 range 从 0 开始。
- 最后一个 range 到文本逻辑长度结束。
- range 有序、非空、连续、不重叠。
- 每个 range 都携带完整的基础字体和描边信息。
- 多规则重叠时默认 longest-match，再按显式 priority 决定。
- 同一短语的多次出现默认全部匹配，可由 job 限制 occurrence。
- 首版采用 literal + Unicode NFKC 匹配，脚本不自行猜测产品名或利益点。

剪映对 emoji/补充平面字符究竟使用 Unicode code point 还是 UTF-16 code unit 计数，需要用独立 fixture 验证；验证前不要宣称支持含此类字符的富文本范围。

## 推荐 Skill 架构

建议创建独立 Skill `jianying-preprocessing`，不直接修改已安装的 `jianying-editor`：

```text
jianying-preprocessing/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/
│   ├── preprocess_draft.py
│   ├── derive_profile.py
│   └── jypre/
│       ├── bundle.py
│       ├── planner.py
│       ├── transaction.py
│       ├── validate.py
│       └── operations/
│           ├── relink.py
│           ├── risk_overlay.py
│           ├── subtitles.py
│           └── highlights.py
├── profiles/
│   └── taobao-flash-v1.json
├── references/
│   ├── config-schema.md
│   ├── draft-v5.9.md
│   └── permission-troubleshooting.md
└── tests/
```

`SKILL.md` 只保留触发条件、路由、授权边界和必要不变量；详细 Draft schema、配置和权限排障放在 references；重复且脆弱的 JSON 操作必须由确定性脚本完成。

### 不直接依赖 `JyProject.save()` 的原因

现有 `jianying-editor` 可复用只读 inspector、路径探测和部分媒体分析思路，但不适合作为本 Skill 的提交引擎：

- `reconnect_all_assets` 尚未实现。
- `add_rich_text` 面向新建字幕，不是批量修改已有字幕。
- `JyProject` 的默认 `overwrite=True` 对已有工程危险。
- 已有草稿 load 失败时存在重新创建路径。
- 对工程 2 只执行 load + dumps，现有库就会把风险 video track 排到字幕 track 之前。
- 它只保存 `draft_info.json`，不会原生维护风险素材所需 sidecar。
- 保存过程还包含额外 patch 行为，不适合作为最小变更事务。

推荐使用 Python 标准库实现“保留未知字段的定向 JSON patch”，ffprobe 只负责媒体验证。

## CLI 设计

建议一个入口、五个模式：

```text
python scripts/preprocess_draft.py inspect  --draft <path>
python scripts/preprocess_draft.py plan     --job <job.json>
python scripts/preprocess_draft.py apply    --job <job.json>
python scripts/preprocess_draft.py validate --draft <path> --job <job.json>
python scripts/preprocess_draft.py rollback --draft <path> --run-id <id>
```

### `inspect`

只读输出：

- Draft 版本和画布。
- 轨道、片段和素材统计。
- 视频 path 状态及 ffprobe 信息。
- dangling/duplicate IDs。
- 候选字幕轨。
- 现有风险图层。
- 字体资源可用性。
- `draft_info.json` 与 `template-2.tmp` 的 hash 关系。

### `plan`

绝不写文件。输出：

- 输入文件 base SHA-256。
- 目标视频解析结果和歧义。
- 将修改的 JSON path 白名单。
- 风险图新增或更新计划。
- 字幕命中数量。
- 产品名和每条利益点的命中数量。
- 未命中、重叠、字体缺失和权限分类。
- 预计修改的 sidecar 文件。

### `apply`

- 要求目标工程未在剪映编辑页打开；首版可要求剪映完全关闭。
- 重新校验 base SHA，避免 plan 后工程被改动。
- 先备份将修改的文件。
- 在内存中生成全部目标文件。
- 写同目录临时文件、flush、fsync，再 `os.replace`。
- 多文件任一验证失败时自动 rollback。

### `validate`

除静态结构校验外，最终验收仍应在克隆 Draft 中打开剪映：

- 无红色离线/不支持媒体。
- 风险图透明且覆盖全片。
- 字幕位置、缩放、换行正确。
- 产品名与利益点颜色/描边正确。
- 保存一次后结构仍闭合。
- 工程封面得到刷新。

## Profile 与 Job 配置

建议分为两层。

### 可复用 Profile

存放稳定的视觉和协议参数：

```json
{
  "profile_schema": 1,
  "name": "taobao-flash-v1",
  "draft_compatibility": {
    "app_version": "5.9.0",
    "draft_version": 360000
  },
  "subtitle": {
    "font": {
      "resource_id": "6740439840254333443",
      "title": "特黑体",
      "filename_hint": "特黑体-思源黑体1号.otf"
    },
    "size": 5,
    "fill": "#FFFFFF",
    "stroke": "#000000",
    "stroke_width": 0.08,
    "line_spacing_raw": 0.25,
    "scale_x": 2.5,
    "scale_y": 2.5,
    "transform_x": 0.0,
    "transform_y": -0.390625
  },
  "product_highlight": {
    "fill": "#FFDE00",
    "stroke": "#000000"
  },
  "risk_overlay": {
    "start_us": 0,
    "duration": "draft",
    "require_canvas_size": true,
    "layer": "above_subtitles"
  }
}
```

`line_spacing_raw` 明确表示 Draft JSON 原始值，避免把 UI 显示值和内部值混用。

### 每次运行 Job

```json
{
  "job_schema": 1,
  "draft_path": "/absolute/path/to/target-draft",
  "profile": "taobao-flash-v1",
  "media_manifest": "/absolute/path/to/media-manifest.json",
  "search_roots": [],
  "media_strategy": "reference-existing",
  "permission_strategy": "diagnose-only",
  "risk_png": "/absolute/path/to/risk-warning.png",
  "subtitle_track": {
    "name": "字幕",
    "on_ambiguous": "fail"
  },
  "line_break_rules": [
    {
      "literal": "，还可以叠加",
      "replacement": "\n还可以叠加"
    }
  ],
  "product_terms": [
    {
      "literal": "淘宝闪购",
      "aliases": [],
      "priority": 100
    }
  ],
  "benefit_rules": [
    {
      "literal": "25元无门槛红包",
      "fill": "#FFDE00",
      "stroke": "#000000",
      "priority": 80
    },
    {
      "literal": "九折津贴卡",
      "fill": "#FFFFFF",
      "stroke": "#FF1837",
      "priority": 80
    }
  ],
  "strict": {
    "unmatched_product": true,
    "unmatched_benefit": true,
    "font_missing": true
  }
}
```

## 事务与文件同步

可能修改的文件：

- `draft_info.json`
- `draft_meta_info.json`
- `key_value.json`
- `draft_virtual_store.json`，可能原先不存在
- `template-2.tmp`，仅条件性同步

不应主动覆盖：

- `.backup/*`
- 剪映维护的历史 `.bak`
- `draft_cover.jpg`
- 未分类的二进制 `draft.extra`

当前两个样本中，`draft_info.json` 与 `template-2.tmp` 分别完全同 hash。因此规则应为：

1. Plan 时记录两者 hash。
2. 如果 apply 前仍相等，则对 `template-2.tmp` 同步相同的 Draft 内容补丁。
3. 如果修改前不相等，默认不覆盖并报告冲突。

事务备份必须记录：

- 每个原文件的内容和 mode。
- 哪些目标文件原先不存在。
- 本次 run ID、base hash 和计划白名单。
- 若做最小权限调整，记录旧 mode。

## 幂等性

重复运行同一 Job 必须得到 no-op：

- 已连接到同一媒体内容时不重写 path。
- 已存在相同风险图层时更新或复用，不新增第二条。
- 字幕样式每次从语义规则重建，不在旧 styles 上继续叠加。
- Range 结果排序和序列化应确定性稳定。
- Sidecar ID 映射应从已存在记录复用，新增时使用稳定生成策略。
- Apply 后再次执行 plan，不应产生待修改项。

风险图层不应仅依赖空 track name 检测。可综合使用：

- 配置的语义用途。
- 图片内容 hash。
- `type=photo`。
- 从 0 覆盖全片的 segment。
- 已记录的 sidecar 映射。

## 校验清单

### JSON 与版本

- 所有目标 JSON 可解析。
- App/draft version 在白名单内。
- 非白名单版本仅允许 inspect/plan。
- 未知字段保持不变。

### ID 与引用

- 各 material 集合内部 ID 唯一。
- Segment ID 唯一。
- 所有 `segment.material_id` 可解析。
- 所有 `extra_material_refs` 可解析。
- 风险图 sidecar 映射闭合。

### 时间线

- 所有 timerange 非负。
- Draft duration 覆盖最大 segment end。
- 原业务视频和字幕时间线未改变。
- 风险图 segment 唯一，且为 `0..draft.duration`。

### 媒体

- 文件存在、可 open。
- ffprobe 可解析。
- 候选媒体的宽高、音频、时长和 manifest 一致。
- PNG 具有 alpha；默认要求尺寸与画布一致。

### 字幕

- 字幕轨选择唯一。
- 预期的全部字幕 segment 命中。
- Material/segment 数量未意外改变。
- 字体路径存在且 resource ID 一致。
- 样式 ranges 连续、无重叠并覆盖全文。
- 产品名和利益点命中数量符合 strict 策略。

### 变更范围

- Semantic diff 只能落在 plan 的允许路径。
- 非目标轨道、片段 ID、时间范围和素材均保持不变。
- 二次 plan 为 no-op。

## 首版非目标

- 不支持任意未知剪映版本。
- 不修改系统 TCC 数据库。
- 不通过复制 `com.apple.macl` 绕过授权。
- 不自行猜测产品名或利益点。
- 不重新识别、生成或调整字幕时间轴。
- 不自动修改视频画面、音频、变速或剪辑点。
- 不覆盖前置 Skill 未授权的其他工程。

## 实施顺序

建议按以下顺序开发：

1. `derive_profile.py`：从 before/after 样本按稳定 ID 对齐并输出 Profile，同时报告未分类差异。
2. `inspect`：实现完全只读的版本、引用、媒体和字幕检查。
3. `plan`：实现确定性媒体解析、高亮匹配及变更白名单。
4. 字幕样式与富文本 range patch。
5. 风险图及 sidecar patch。
6. 原子事务、rollback 和幂等性。
7. POSIX 权限的最小修复分支。
8. 剪映原生 TCC/重连 UI 分支。
9. 在新的克隆工程中打开剪映做视觉验收。
10. 验证保存一次、关闭、重新打开后工程结构和视觉效果仍正确。

## 实现前需要确认的业务选择

1. 前置 Skill 是否保证传入的是可修改的工程副本。
2. 首版是否只支持剪映 5.9.0。
3. 风险提示图是否始终与画布同尺寸、透明并覆盖全片。
4. “特黑体 + 当前参数”是否作为唯一默认 Profile。
5. 产品名、别名和利益点是否由前置 Skill 明确传入。
6. 未命中的产品名/利益点应警告还是整次失败。
7. TCC 失败时是否允许自动打开剪映并通过原生文件选择器授权。
8. 是否允许将媒体 clone/copy 到 Draft staging 作为无人值守兜底。

## 当前建议

- 由前置 Skill 负责生成可修改的目标工程副本和精确媒体 manifest。
- 本 Skill 默认在目标副本内事务化处理，但仍创建自己的可回滚备份。
- 首版锁定剪映 5.9.0 / Draft 360000。
- 先交付 inspect/plan，再开启 apply。
- 高亮只执行上游提供的明确短语。
- 权限默认 diagnose-only；TCC 分支不宣称可以通过 chmod 修复。
- 最终完成条件必须包含一次剪映内的真实打开和视觉验收。

