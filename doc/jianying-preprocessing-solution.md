# 剪映工程预处理 Skill：样本研究与实现方案

## 文档状态

- 状态：v0.1 已开始实现；已固化配置校验、inspect/plan/apply/validate/rollback、字幕样式与高亮、利益点图片、风险提示及事务/幂等回归
- 研究日期：2026-09-07
- 需求修订：已纳入可切换配置集、跨类别强校验、可空利益点图片/风险提示/尾帧及逐视频分段尾帧接口
- 首版目标版本：剪映专业版 5.9.0，`draft_info.json.version = 360000`
- 研究方式：只读检查三个本地剪映工程、工程备份时间序列、媒体文件及现有 `jianying-editor` 能力

### 当前实现边界（v0.1）

- 已实现：Catalog 统一管理、单项目中文注释 `config.jsonc`、Catalog/Config Set/六类组件 closed JSON Schema、首个 approved 配置集、Job 防内联校验、只读 Draft 检查、锁定计划、字幕样式/换行/产品与利益点高亮、利益点图片、风险提示、状态归属、原子多文件写入、自动 rollback、显式 rollback、二次 plan no-op。
- 已实现并由本机三个样本回归：1/2/3 的结构统计；工程1临时副本处理后得到5轨/138段、22个 video/photo material、11个 material animation，10次产品名和各10次利益点命中，随后可幂等复跑并完整回滚。
- 已定义并实现规划代码、但首个配置集未启用：3秒逐分段尾帧、末段延长和最终风险层覆盖。
- 尚未实现：media manifest/search root 重连、POSIX owner 权限修复、剪映原生 TCC 授权、staging clone/copy、剪映 UI 内视觉验收自动化。v0.1 对这些模式显式失败，不静默降级。
- 原始参考工程 1/2/3 始终只读；自动写入测试仅针对临时副本。

## 目标

前置 Skill 会准备好一个有效的剪映工程。本 Skill 对该工程进行预处理：

1. 将时间线视频连接到对应文件；若失败是权限问题，进行可审计的最小修复或引导原生授权。
2. 添加风险提示图，通常为透明 PNG。
3. 统一字幕的字体样式、行间距、缩放和位置。
4. 添加产品名高亮。
5. 添加利益点高亮。
6. 按配置决定是否在每个业务视频分段结束后添加 3 秒固定尾帧图。
7. 按字幕中的利益点命中结果，在对应字幕时段添加利益点图片。

产品名、利益点、利益点图片、风险提示图和尾帧图都不得写死在执行代码中。首版将当前淘宝闪购样本固化为第一个有版本号的配置集；后续通过切换配置集复用同一执行器。利益点图片、风险提示和尾帧允许显式配置为 `null`，其含义是本次期望状态中不应存在由本 Skill 管理的该类内容：新工程不添加，已处理工程则删除旧的托管对象。

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

### 增加利益点图片后的工程

```text
/Users/sakana/Movies/JianyingPro/User Data/Projects/com.lveditor.draft/3
```

三个样本均为：

- 剪映专业版：5.9.0
- Draft version：360000
- 画布：720 × 1280，9:16
- 帧率：30 fps
- 工程时长：7535 帧；Draft 原始值为 251166666 微秒
- 源工程：3 条轨道、127 个片段
- 工程 2：4 条轨道、128 个片段
- 工程 3：5 条轨道、138 个片段

工程 2 是工程 1 的副本，工程 3 继续基于工程 2 增加利益点图片。`draft_info.json` 内部工程 ID 被保留，但 `draft_meta_info.json.draft_id`、工程名及目录元数据发生了复制相关变化。这类差异不是预处理规则。

## 样本结论总览

| 功能 | 样本中观察到的处理 | 实现含义 |
|---|---|---|
| 视频重连 | 10 个视频的绝对路径、素材主键、片段主键和时间线均未变化 | 不能仅凭 `path` 判断是否已连接 |
| 风险提示 | 新增 1 个 photo material、1 条 video track、1 个全片 segment 及辅助素材 | 不能只向 JSON 增加一个图片路径 |
| 字幕样式 | 116 条字幕统一字体、描边、行间距 | 需同时修改 text material 和 text segment |
| 字幕布局 | 116 条字幕统一缩放和位置 | 布局在 segment 的 `clip` 中，不在 text material 中 |
| 产品名高亮 | 10 处“淘宝闪购”变为黄色 | 需生成完整、连续的富文本 range |
| 利益点高亮 | 两个利益点使用不同视觉样式 | 利益点规则必须支持逐短语配置，而非一个全局颜色 |
| 利益点图片 | Draft 3 新增 1 条轨道、10 个 photo segment，并与10条利益点字幕逐一同区间 | 图片触发条件应引用利益点 ID，时长跟随匹配字幕，不能重复维护自然语言短语 |
| 换行 | 10 处利益点字幕由逗号改为换行 | 应作为显式规则，不能当作高亮的隐式副作用 |
| 配置隔离 | 当前样本只有一套业务内容，但后续需要切换 | 产品名、利益点、利益点图片、风险提示和尾帧必须使用带类型的配置文件，Job 不得内联这些内容 |
| 防混用校验 | 业务类别容易被生成式调用方误填 | 先校验 schema、`kind`、配置集归属、跨类别冲突和资产指纹；失败时不得修改 Draft |
| 尾帧接口 | 当前处理后样本没有尾帧，源视频轨有 10 个业务分段 | 只能先定义选择器、3 秒插入语义、冲突策略和幂等映射，不能伪装成已从样本验证 |
| 可空功能 | 部分配置不需要利益点图片、风险图或尾帧 | 仅显式 `null` 表示关闭；字段缺失是配置错误，不得猜测默认值 |

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

## 时间基准：以帧判断，以微秒读写

剪映 5.9 的 `target_timerange` 和 `source_timerange` 使用整数微秒序列化，但工程 `fps = 30.0`，画面片段的边界必须按帧率解释。实现规则是：

- Draft 原始微秒值是读写格式，不能改成帧数直接写入 JSON。
- 新增片段、工程延长和碰撞判断必须验证起止点是否对应整数帧边界。
- 30 fps 下一帧是循环出现的 33333/33334 微秒间隔，不能反复累加固定的 33333 微秒。
- 对绝对帧边界 `n`，当前样本符合 `floor(n × 1000000 / 30)`；由开始和结束边界分别换算后再相减，不能独立假定每帧具有相同整数微秒长度。
- 配置仍可表达业务上的整秒时长，例如尾帧 `duration_us = 3000000`；校验器必须确认它在目标 Draft 中恰好等于90帧。
- 已有字幕时间范围不做量化或改写；需要判断视觉片段碰撞时，只将其映射为所占用的帧区间。

Draft 3 提供了一个不可忽略的实例：第10个利益点图片 segment 的 `source_timerange.duration = 3933333`，`target_timerange.duration = 3933334`。两者都覆盖118帧，1微秒差异来自目标片段绝对起始帧的取整相位。因此校验器应比较帧区间，不得要求 source/target 的原始 duration 数字逐字相等，也不得擅自把其中一个复制给另一个。

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

尺寸不匹配时默认阻止 apply。若后续需要支持 `fit`、`fill` 或坐标变换，必须将策略加入对应风险提示配置和 Schema，不能由 Job 临时覆盖，也不能静默拉伸。

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

其中 `line_spacing = 0.25` 对应剪映界面行间距5。当前只验证了这一个界面值与 Draft 原始值的映射，首版不应据此猜测其他行间距的换算规律。

字体资源：

```text
名称：特黑体
Resource ID：6740439840254333443
本机文件：特黑体-思源黑体1号.otf
```

字体缓存绝对目录包含机器相关 hash，字幕样式配置不应只硬编码完整路径。运行时应按以下顺序解析：

1. 字幕样式配置中的 resource ID、名称和 filename hint。
2. 剪映缓存目录中的 resource ID/文件名与可选文件 hash。
3. 无唯一结果时阻止 apply；不得从 Job 或自然语言临时替换字体。

不要在未确认字体授权的情况下把字体文件直接打包进 Skill。

### Content 样式

基础字幕语义为：

- 字号：`content.styles[].size = 5`
- 字色：白色 `#FFFFFF`
- 描边：黑色 `#000000`
- 描边宽度：约 `0.08`
- 字体：特黑体 resource ID `6740439840254333443`
- `useLetterColor = true`

工程中的 `preset_id`、`text_preset_resource_id`、`preset_name`、`style_name` 仍为空。因此这里不是引用一个剪映动态预设，而是把样式实体化到每一个字幕 material。Skill 内应使用带版本的 `subtitle_style` 配置表达这个预设。

### Segment 布局变化

116 个字幕 segment 全部发生：

```text
clip.scale.x: 1.0 -> 2.5
clip.scale.y: 1.0 -> 2.5
clip.transform.x: 0.0 -> 0.0
clip.transform.y: -0.8 -> -0.390625
```

在固定720×1280画布下，处理后数值对应剪映界面位置 `x=0, y=-500` 和缩放250%。其中 `-500 / 1280 = -0.390625`，`250 / 100 = 2.5`。

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

## 利益点图片研究

### Draft 2 → Draft 3 的最小语义差异

Draft 3 在 Draft 2 的基础上新增：

- 1 条 `type=video` 的图片轨，共10个 segment。
- 10 个 `materials.videos[type=photo]`。
- 10 个 canvas、10 个 speed、10 个 `material_animation`、10 个 sound channel mapping、10 个 vocal separation。
- `draft_meta_info.json` 中1条本地 photo 导入记录。
- `key_value.json` 中10条 segment-to-asset 记录。
- `draft_virtual_store.json` 中1条本地素材父子关系。

新增轨道 ID 为 `F111B9AA-3109-4385-BAF7-689B535424A0`，name 为空，`type=video`、`flag=2`，包含10个 segment。首版不能依赖空 name 识别该轨道，应依赖 Skill 状态和对象映射。

原有对象只发生层级顺延：116个字幕 segment 的 `track_render_index` 从2变为3，风险提示 segment 从3变为4。原视频、字幕内容、字幕 timerange、风险提示内容及 Draft duration 均未改变。因此新增轨道的明确层级是：

```text
封面/主视频：track_render_index 0
业务视频：   track_render_index 1
利益点图片： track_render_index 2
字幕：       track_render_index 3
风险提示：   track_render_index 4
```

也就是利益点图片在业务视频之上、字幕之下；风险提示仍在最上层。不能只向轨道数组末尾追加图片轨，而不重算受影响的 `track_render_index`。

### 图片资产

```text
路径：/Volumes/Elements SE/陈鼎琦/饿了么整理/素材/贴片/淘宝闪购9折津贴卡-25.png
SHA-256：86a17217483e0bc60545e5377d49e740042e3ce98a685f0af1faac98ebbb4ca3
格式：PNG / RGBA
尺寸：720 × 1280
内容：25元无门槛红包、其他红包档位及9折津贴卡的组合视觉
```

图片与画布同尺寸，但 segment 不是满画布原比例显示，而是使用统一变换：

```json
{
  "scale": {
    "x": 0.8315874938849428,
    "y": 0.8315874938849428
  },
  "transform": {
    "x": 0.0,
    "y": 0.22245762711864403
  },
  "alpha": 1.0,
  "rotation": 0.0
}
```

10个片段还统一使用“便利贴”入场动画：

```json
{
  "type": "in",
  "name": "便利贴",
  "id": "70486392",
  "resource_id": "7379456870265655859",
  "duration": 900000
}
```

以上是 Draft 原始字段；配置中的 `effect_id` 写回 `animations[].id`，`duration_us` 写回 `animations[].duration`。`900000` 微秒在30 fps工程中正好是27帧。动画缓存绝对路径含机器相关 hash，配置只能保存 resource/effect ID、名称和 duration，运行时解析本机资源；无法唯一解析时必须阻止 apply。

### 触发和时间范围

10个图片 segment 分别与10条文本完全相同的字幕一一对应：

```text
最高25元无门槛红包
还可以叠加九折津贴卡
```

图片片段的目标起止时间与对应字幕 segment 完全相同，并且每个业务视频分段恰好命中一次：

| 序号 | 开始帧 | 结束帧 | 帧数 | Draft 原始 start | Draft 原始 duration |
|---:|---:|---:|---:|---:|---:|
| 1 | 286 | 404 | 118 | 9533333 | 3933333 |
| 2 | 1032 | 1152 | 120 | 34400000 | 4000000 |
| 3 | 1875 | 1995 | 120 | 62500000 | 4000000 |
| 4 | 2686 | 2806 | 120 | 89533333 | 4000000 |
| 5 | 3455 | 3575 | 120 | 115166666 | 4000000 |
| 6 | 4257 | 4374 | 117 | 141900000 | 3900000 |
| 7 | 5007 | 5122 | 115 | 166900000 | 3833333 |
| 8 | 5762 | 5882 | 120 | 192066666 | 4000000 |
| 9 | 6542 | 6662 | 120 | 218066666 | 4000000 |
| 10 | 7349 | 7467 | 118 | 244966666 | 3933334 |

这不是“看到任意利益点就显示固定4秒”，而是“满足一组利益点条件的字幕出现多久，图片就显示多久”。建议的数据流为：

1. 执行利益点配置中的显式换行规则。
2. 在最终字幕文本中匹配利益点 literal，得到命中的 `benefit_id` 集合。
3. 利益点图片规则只引用 `benefit_id`，不再复制“25元无门槛红包”等自然语言。
4. 当同一字幕同时满足规则要求的全部 `benefit_id` 时，创建一个图片片段。
5. 图片 `target_timerange` 直接跟随该字幕的目标区间，但写入前进行帧边界校验。
6. 将匹配字幕 segment ID、利益点图片规则 ID 和新图片 segment ID 写入 Skill 状态，支持幂等更新和配置切换删除。

### Draft material 与 sidecar 关系

虽然10个 segment 使用同一文件，剪映原生结果仍创建了10个不同的 `materials.videos` ID，并为每个 segment 创建一套辅助 material。与此同时：

- `draft_meta_info.json` 只新增1条资产导入记录，ID 为 `c1ae4089-c4b3-4dca-a5b1-e51b9bf7d2c0`。
- `draft_virtual_store.json` 只新增这1个 asset child ID。
- `key_value.json` 新增10条以 segment ID 为 key 的记录，但它们共享 asset-level `materialId = 590927c08fdf097716ab176752bbe5ca`。
- 每个 photo material 的静态素材 duration 为 `10800000000`；实际展示时间由 segment 的 source/target timerange 决定。

这些 UUID 和 asset-level ID 只是样本证据，不能硬编码。还要注意三种 duration 并不表达同一含义：`draft_meta_info` 的本地导入记录为 `5000000`，`materials.videos` 的静态图片素材为 `10800000000`，时间线 segment 则跟随字幕约115–120帧。实现不能为了“统一”而把三者改成同一个数值。

首版应复现这一已观察到的原生形态：每个命中字幕一个 photo material 和一套辅助 material，但同一图片文件只登记一次 meta/virtual-store 资产身份。是否能安全让多个 segment 共享同一个 `materials.videos` 对象尚未由样本验证，不作为首版优化。

## 当前样本中的“视频分段”与尾帧边界

这里不按素材文件数量猜分段，而是使用以下确定性定义：

> “视频分段”是配置选中的业务视频轨上，引用 `materials.videos[type=video]` 的原始 segment；不包含封面占位、风险提示图片、尾帧图片和其他 photo segment。

在当前三个样本里，选择器都可唯一定位到 Track name 为 `视频素材`、Track type 为 `video` 的轨道，共10个业务视频 segment。下表以30 fps下的整数帧为主单位；Draft 中的微秒仅作为序列化结果：

| 序号 | 开始帧 | 帧数 | 结束帧 | 到下一业务视频的空档帧数 |
|---:|---:|---:|---:|---:|
| 1 | 0 | 452 | 452 | 300 |
| 2 | 752 | 494 | 1246 | 300 |
| 3 | 1546 | 504 | 2050 | 300 |
| 4 | 2350 | 505 | 2855 | 300 |
| 5 | 3155 | 514 | 3669 | 300 |
| 6 | 3969 | 491 | 4460 | 300 |
| 7 | 4760 | 428 | 5188 | 300 |
| 8 | 5488 | 466 | 5954 | 300 |
| 9 | 6254 | 500 | 6754 | 300 |
| 10 | 7054 | 481 | 7535 | 无；恰好为 Draft 终点 |

116 条字幕也可以按这 10 段归组，每组最后一条字幕都恰好在对应业务视频结束处结束，10 秒空档内没有字幕。因此：

- 前9段后的空档均为300帧；添加90帧图片不会与下一视频或字幕碰撞，也无需平移原片段。
- 第10段没有尾部空间。业务已确认尾帧开启时从7535帧延长到7625帧，并在 `[7535, 7625)` 添加完整90帧尾帧；对应 Draft 原始边界为 `[251166666, 254166666)` 微秒。
- 处理后参考工程本身没有尾帧，无法用 before/after 差异判断最后一段的业务选择。
- 业务已确认：若风险提示配置非空，风险提示图必须覆盖包括新增尾帧在内的最终 Draft 时长。

因此首版尾帧接口把末段策略固定为 `extend_draft`，风险图覆盖策略固定为 `final_draft`。二者仍写入配置以便审计，但执行器不得自行选择其他行为。

## 配置体系：统一目录、单项目单文件、带类型、可切换、不可内联

### 设计目标

配置体系需要同时满足：

1. 业务内容可随时按 `config_set_id` 切换，执行代码不改动。
2. 每个业务项目只维护一份带中文注释的 `config.jsonc`；字幕、产品名、利益点、利益点图片、风险提示和尾帧在文件内仍是独立带类型组件。
3. Job 只选择已存在的配置集，不允许临时内联业务短语、图片路径或样式，避免生成式调用方把类别混用。
4. `configs/catalog.jsonc` 是配置集统一索引；项目 ID 只在配置集顶层声明一次，组件由所在槽位和 `kind` 双重判别，跨目录路径和未知字段一律拒绝。
5. `benefit_images`、`risk_warning` 和 `end_frame` 的关闭方式只有显式 JSON `null`；字段缺失不是关闭，而是配置不完整。
6. 先完整加载并校验配置，再读取并规划 Draft；配置错误时不得产生任何工程写入。

需要明确：校验器无法仅凭语言学判断任意短语究竟是不是“产品名”。语义真值必须来自人工确认并纳入版本控制的类型化配置。防幻觉的关键是让 Codex 只能选择已批准配置集，不能在 Job 或运行时生成、改写、补全这些值；校验器负责阻断结构混用、跨集拼装、重复短语、资产错配和未批准配置。

### 当前目录

```text
configs/
├── catalog.jsonc
├── taobao-flash-v1/
│   └── config.jsonc
└── <another-config-set>/
    └── config.jsonc
schemas/
├── catalog.schema.json
├── config-set.schema.json
├── subtitle-style.schema.json
├── product-names.schema.json
├── benefit-points.schema.json
├── benefit-images.schema.json
├── risk-warning.schema.json
└── end-frame.schema.json
```

总目录记录配置集 ID、显示名、说明、标签、相对路径和启用状态。一个配置集被禁用时仍可列出和校验，但不能进入 plan/apply。配置路径必须位于 `configs/` 内，禁止绝对路径、`..` 和符号链接逃逸。

### Config Set 契约

当前参考样本作为首个配置集：

```jsonc
{
  // 单个项目的全部可编辑配置集中在此文件。
  "schema_version": 1,
  "kind": "preprocess_config_set",
  "config_set_id": "taobao-flash-v1",
  "display_name": "淘宝闪购-星广",
  "approval": {
    "status": "approved",
    "source": "reference_draft_diff"
  },
  "draft_compatibility": {
    "app_version": "5.9.0",
    "draft_version": 360000,
    "fps": 30
  },
  "subtitle_style": {"kind": "subtitle_style", "...": "..."},
  "product_names": {"kind": "product_names", "items": []},
  "benefit_points": {"kind": "benefit_points", "items": [], "line_break_rules": []},
  "benefit_images": {"kind": "benefit_images", "items": []},
  "risk_warning": {"kind": "risk_warning", "...": "..."},
  "end_frame": null
}
```

Config Set 使用 closed schema，即 `additionalProperties: false`。六个组件槽位都必须出现：`subtitle_style`、`product_names` 和 `benefit_points` 必须是对象；`benefit_images`、`risk_warning` 与 `end_frame` 可为对应类型对象或 `null`。`.jsonc` 仅增加注释能力，不允许尾随逗号；注释不会进入 Draft。Catalog、完整配置源文件及每个解析后组件分别参与 plan 哈希锁。

`null` 的精确定义：

- `"benefit_images": null`：目标 Draft 的期望状态中不存在 Skill 托管利益点图片；新工程不新增，切换配置时删除此前由本 Skill 创建且可验证归属的图片轨、photo material、segment、动画、辅助 material 和 sidecar 映射。
- `"risk_warning": null`：目标 Draft 的期望状态中不存在 Skill 托管风险图；新工程不新增，切换配置时删除此前由本 Skill 创建且可验证归属的风险图对象。
- `"end_frame": null`：目标 Draft 的期望状态中不存在 Skill 托管尾帧；新工程不新增，切换配置时删除此前由本 Skill 创建且可验证归属的尾帧素材、轨道、片段和 sidecar 映射。
- 字段缺失、空字符串、空对象、字符串 `"null"` 都是错误。
- 可空只作用于整个功能，不接受“配置文件存在但 asset.path 为空”这种半关闭状态。

### 当前字幕样式配置

```json
{
  "schema_version": 1,
  "kind": "subtitle_style",
  "canvas": {
    "width": 720,
    "height": 1280,
    "policy": "require_exact"
  },
  "font": {
    "resource_id": "6740439840254333443",
    "title": "特黑体",
    "filename_hint": "特黑体-思源黑体1号.otf"
  },
  "size": 5,
  "fill": "#FFFFFF",
  "stroke": "#000000",
  "stroke_width": 0.08,
  "layout_ui": {
    "position": {
      "x": 0,
      "y": -500,
      "unit": "canvas_pixel"
    },
    "scale_percent": 250,
    "line_spacing": 5
  }
}
```

首个配置集使用剪映界面单位作为业务真值，默认值明确为：

```text
画布：720 × 1280，必须完全一致
位置：x = 0，y = -500
缩放：250%
行间距：5
```

编译到 Draft 时必须生成以下原始值：

```json
{
  "materials.texts[].line_spacing": 0.25,
  "segment.clip.scale.x": 2.5,
  "segment.clip.scale.y": 2.5,
  "segment.clip.transform.x": 0.0,
  "segment.clip.transform.y": -0.390625
}
```

转换契约：

- `scale = scale_percent / 100`。
- 固定画布下 `transform.x = position.x / 720`，`transform.y = position.y / 1280`。
- 当前已验证 `line_spacing UI 5 -> Draft 0.25`；首版转换器应显式支持该映射，而不是把界面值5直接写入 Draft。
- 画布不是720×1280时，`require_exact` 使 apply 失败，不自动缩放位置。
- plan 必须同时输出配置界面值和将写入的 Draft 值，便于人工核对。

### 当前产品名配置

```json
{
  "schema_version": 1,
  "kind": "product_names",
  "items": [
    {
      "product_id": "taobao-flash",
      "literal": "淘宝闪购",
      "aliases": [],
      "priority": 100,
      "style": {
        "fill": "#FFDE00",
        "stroke": "#000000"
      }
    }
  ]
}
```

只允许 literal 精确匹配及配置中明确列出的 aliases。执行器不得根据上下文扩写“淘宝”“闪购”等近似词，也不得让语言模型自动归一化品牌名。

### 当前利益点配置

```json
{
  "schema_version": 1,
  "kind": "benefit_points",
  "items": [
    {
      "benefit_id": "coupon-25-no-threshold",
      "literal": "25元无门槛红包",
      "priority": 80,
      "style": {
        "fill": "#FFDE00",
        "stroke": "#000000"
      }
    },
    {
      "benefit_id": "subsidy-card-90-percent",
      "literal": "九折津贴卡",
      "priority": 80,
      "style": {
        "fill": "#FFFFFF",
        "stroke": "#FF1837"
      }
    }
  ],
  "line_break_rules": [
    {
      "literal": "，还可以叠加",
      "replacement": "\n还可以叠加"
    }
  ]
}
```

换行规则归属于利益点配置，但仍是独立显式操作：只有 literal 完整命中时才替换，不能把换行当成高亮的隐式副作用。

### 当前利益点图片配置

```json
{
  "schema_version": 1,
  "kind": "benefit_images",
  "items": [
    {
      "benefit_image_id": "coupon-and-subsidy-card",
      "requires_benefit_ids": [
        "coupon-25-no-threshold",
        "subsidy-card-90-percent"
      ],
      "match_mode": "all_in_same_subtitle",
      "asset": {
        "path": "/Volumes/Elements SE/陈鼎琦/饿了么整理/素材/贴片/淘宝闪购9折津贴卡-25.png",
        "sha256": "86a17217483e0bc60545e5377d49e740042e3ce98a685f0af1faac98ebbb4ca3",
        "width": 720,
        "height": 1280,
        "require_alpha": true
      },
      "timing": "matched_subtitle_timerange",
      "cardinality": "one_per_business_video_segment",
      "placement": {
        "layer": "below_subtitles_above_business_video",
        "scale_x": 0.8315874938849428,
        "scale_y": 0.8315874938849428,
        "transform_x": 0.0,
        "transform_y": 0.22245762711864403,
        "alpha": 1.0,
        "rotation": 0.0
      },
      "animation_in": {
        "name": "便利贴",
        "effect_id": "70486392",
        "resource_id": "7379456870265655859",
        "duration_us": 900000
      }
    }
  ]
}
```

利益点图片配置只引用 `benefit_id`，不允许再次出现利益点 literal。校验器必须确认每个 ID 在同一 `config.jsonc` 的 `benefit_points.items` 中唯一存在；这样即使调用者混淆“图片上的文案”和“字幕触发词”，也不能绕过已批准的利益点真值。

业务已确认 `benefit_images` 可以为 `null`。关闭功能必须在 `config.jsonc` 中显式写 `null`；非空 `benefit_images.items` 必须至少有一项，不接受空列表作为第二种关闭方式，避免产生两套等价语义。

### 当前风险提示配置

```json
{
  "schema_version": 1,
  "kind": "risk_warning",
  "asset": {
    "path": "/Volumes/Elements SE/陈鼎琦/饿了么整理/风险提示语排版/淘宝闪购星广提示语.png",
    "sha256": "88cef1bb4d34c4bbdd35048cfed01d40f2d4bf55bcd37c6967db25f3113745e4",
    "width": 720,
    "height": 1280,
    "require_alpha": true
  },
  "placement": {
    "start_us": 0,
    "duration": "draft",
    "layer": "above_subtitles"
  }
}
```

路径用于定位，SHA-256 才用于确认内容身份。配置切换后即使文件名相同，只要 hash 不同也必须视为资产变化。图片路径、hash、尺寸或透明通道不符合配置时应失败，不能静默使用同目录下的“相似图片”。

### 尾帧配置接口

当前首个配置集的 `end_frame` 为 `null`。下例定义后续配置集启用尾帧时的已确认接口：

```json
{
  "schema_version": 1,
  "kind": "end_frame",
  "asset": {
    "path": "/absolute/path/to/end-frame.png",
    "sha256": "<64位小写十六进制SHA-256>",
    "width": 720,
    "height": 1280
  },
  "duration_us": 3000000,
  "placement": "after_each_video_segment",
  "segment_selector": {
    "track_type": "video",
    "track_name": "视频素材",
    "material_type": "video"
  },
  "collision_policy": "require_gap",
  "last_segment_policy": "extend_draft",
  "risk_overlay_coverage": "final_draft"
}
```

真正进入已批准配置时，`asset.sha256` 必须替换为真实指纹。首版 Schema 的时间线策略为：

- `collision_policy`：首版仅支持 `require_gap`。尾帧区间与下一业务视频、已有图片或字幕发生碰撞时整次失败，绝不静默平移原片段。
- `last_segment_policy`：首版固定为 `extend_draft`。末段空间不足时将 Draft duration 延长到容纳完整 3 秒尾帧，不允许跳过末段。
- `risk_overlay_coverage`：首版固定为 `final_draft`。只有风险配置非空时生效，风险图 duration 必须在尾帧规划完成后按最终 Draft duration 计算。

尾帧的计划算法：

1. 用 `segment_selector` 唯一选中业务视频轨；选择到 0 条或多条轨道都失败。
2. 将每个 `material_type=video` 原始 segment 的目标结束边界解析为整数帧；当前30 fps样本中的3秒尾帧经校验等于90帧。
3. 在帧域生成 `[source_end_frame, source_end_frame + 90)`，再由两个绝对帧边界分别序列化为 Draft 微秒；禁止逐帧累加33333微秒。
4. 检查与下一业务视频、字幕和非本 Skill 管理片段的碰撞。
5. 同一张 photo material 可被多个尾帧 segment 复用，但每个源 segment 必须对应一个独立尾帧 segment。
6. 尾帧放在 Skill 管理的独立 video track 中，避免改变原业务视频 track、剪辑点和 segment 类型。
7. 原业务视频和原字幕 timerange 保持不变；除非后续另行批准“整体平移”能力，首版完全不提供这种策略。
8. 末段按 `extend_draft` 延长工程；随后重新计算所有依赖 Draft duration 的托管层，非空风险提示必须覆盖最终工程时长。

### 配置切换和 Skill 管理状态

为了支持“后续随时切换”，仅靠图片特征或空 track name 无法安全判断哪些内容可以更新或删除。建议在目标工程中维护 Skill 自有的状态文件：

```text
.jypre/state.json
```

状态只记录本 Skill 创建或接管的对象，不成为业务配置真值。至少包含：

- 上次成功应用的 `config_set_id`。
- bundle 及每个组件文件的 SHA-256。
- apply 时的 Draft base/result hash。
- 风险图 material、track、segment 与 sidecar ID。
- 每个匹配字幕 segment ID 到利益点图片规则、photo material、图片 segment 和辅助 material ID 的映射。
- 每个源视频 segment ID 到尾帧 segment ID 的映射。
- 事务 run ID 和工具 schema 版本。

切换配置时先做 desired-state reconciliation：

- 新旧组件内容相同则复用现有托管对象。
- 新配置更换图片或样式时，只更新状态文件中记录且仍通过身份校验的托管对象。
- 状态缺失、对象被人工修改或归属验证失败时，禁止自动删除，要求重新 plan 或人工确认。
- 对非本 Skill 创建的相似图层永不凭视觉特征直接删除。

利益点图片、风险提示或尾帧从非空切换为 `null` 时，必须删除此前由本 Skill 创建且仍能验证归属的对应对象和 sidecar 映射。删除必须出现在 plan 的白名单中并纳入事务备份；如果状态缺失、对象身份不匹配或无法证明归属，则整次 apply 失败，绝不删除疑似由用户手工创建的内容。目标工程从未添加过该类托管对象时，`null` 是严格 no-op。

### 操作依赖顺序

单次 plan/apply 应按数据依赖生成最终状态：

1. 校验配置集、资源、Draft 版本与基础 hash。
2. 解析并重连业务视频，但不改变时间线。
3. 应用字幕换行、基础样式、产品名和利益点高亮，产生每条字幕的稳定 `benefit_id` 命中集合。
4. 根据命中集合规划利益点图片，并直接继承匹配字幕的目标时间范围。
5. 规划每个业务视频后的尾帧，并计算最终 Draft duration。
6. 按最终 Draft duration 规划风险提示覆盖范围。
7. 统一重算托管轨道层级和所有受影响的 `track_render_index`。
8. 完整校验内存中的目标文件后再开启事务写入。

这样可以避免利益点图片在字幕改写前匹配、风险提示只覆盖旧时长，或后插轨道导致已有 segment render index 失效。

## 配置校验器

### 校验顺序

`validate-config` 必须在 Draft 写操作之前完成以下层级：

1. **语法和 Schema**：JSON 可解析、schema version 支持、closed schema、必填字段齐全、类型正确。
2. **类型判别**：Config 各槽位的 `kind` 必须分别精确等于 `subtitle_style`、`product_names`、`benefit_points`、`benefit_images`、`risk_warning`、`end_frame`。
3. **配置集一致性**：顶层 `config_set_id`、`display_name` 必须与 Catalog 条目一致，配置路径必须受限于配置根目录。
4. **批准状态**：只允许 `approval.status=approved` 的 Config Set 进入 apply；草稿配置可以 inspect/validate，但不能写 Draft。
5. **类别互斥**：产品名与利益点的标准化 literal/alias 不得完全相同；如未来确有重叠需求，必须新增显式且可审计的例外机制，首版不接受。
6. **字段隔离**：产品名/利益点配置禁止出现资产字段；利益点图片允许资产和 `benefit_id` 引用但禁止 literal；风险/尾帧配置禁止出现短语、高亮和换行字段；未知字段直接失败。
7. **跨文件引用**：利益点图片的每个 `requires_benefit_ids` 必须在同一配置集的利益点文件中唯一存在，不允许悬空 ID、重复 ID 或引用产品 ID。
8. **资产身份**：文件存在且可读，SHA-256、尺寸、格式符合配置；风险图和当前利益点图片必须有 alpha；利益点图片、风险图与尾帧默认不得解析为相同 path 或相同 hash。
9. **值域和帧对齐**：颜色、缩放、位置和 line spacing 在允许范围；literal 非空且去除首尾空白后不变；ID 唯一；尾帧时长严格为 `3000000` 且在30 fps下为90帧；利益点图片动画 `900000` 为27帧。
10. **Draft 绑定**：轨道选择唯一、素材选择唯一、产品名与利益点命中数满足 strict 策略；当前利益点图片规则必须在每个业务视频分段中恰好命中一条字幕；图片区间与字幕帧区间相同；尾帧区间无冲突。
11. **计划锁定**：plan 输出所有配置文件 hash；apply 前重新计算，任何变化都使计划失效。

### 防混用的失败示例

以下情况均必须在修改 Draft 前失败：

- Job 内出现 `product_terms`、`benefit_rules`、`benefit_image_png`、`risk_png` 或 `end_frame_png` 等内联业务字段。
- `config.product_names` 被错误填成一个 `kind=benefit_points` 的对象。
- `config.benefit_images` 被错误填成风险提示或尾帧对象。
- 利益点图片直接重复 literal，或引用了不存在的 `benefit_id`。
- Catalog 条目指向另一个配置集目录，或其 ID、显示名与 Config Set 顶层不一致。
- 同一 literal 同时出现在产品名和利益点中。
- 利益点图片、风险图或尾帧路径填错，导致本应不同的资产 hash 相同。
- 配置缺字段时由 Codex“根据文件名补全”。
- `null` 被替换为空字符串、空对象或不存在的配置路径。

### 校验结果格式

机器可读结果应至少包含：

```json
{
  "valid": true,
  "config_set_id": "taobao-flash-v1",
  "component_hashes": {
    "bundle": "<sha256>",
    "subtitle_style": "<sha256>",
    "product_names": "<sha256>",
    "benefit_points": "<sha256>",
    "benefit_images": "<sha256>",
    "risk_warning": "<sha256>",
    "end_frame": null
  },
  "resolved_counts": {
    "product_names": 1,
    "benefit_points": 2,
    "benefit_image_rules": 1
  },
  "feature_state": {
    "benefit_images": "configured",
    "risk_warning": "configured",
    "end_frame": "disabled"
  },
  "errors": [],
  "warnings": []
}
```

此处 `feature_state.benefit_images=configured` 表示已加载利益点图片规则；`feature_state.end_frame=disabled` 表示 bundle 中尾帧组件为 `null`，不表示校验失败。

## 推荐 Skill 架构

建议创建独立 Skill `jianying-preprocessing`，不直接修改已安装的 `jianying-editor`：

```text
jianying-preprocessing/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/
│   ├── preprocess_draft.py
│   ├── derive_config.py
│   └── jypre/
│       ├── config_loader.py
│       ├── config_validator.py
│       ├── draft_bundle.py
│       ├── planner.py
│       ├── state.py
│       ├── transaction.py
│       ├── validate.py
│       └── operations/
│           ├── relink.py
│           ├── risk_overlay.py
│           ├── subtitles.py
│           ├── highlights.py
│           ├── benefit_images.py
│           └── end_frame.py
├── configs/
│   ├── catalog.jsonc
│   └── taobao-flash-v1/
│       └── config.jsonc
├── schemas/
│   ├── catalog.schema.json
│   ├── config-set.schema.json
│   ├── subtitle-style.schema.json
│   ├── product-names.schema.json
│   ├── benefit-points.schema.json
│   ├── benefit-images.schema.json
│   ├── risk-warning.schema.json
│   └── end-frame.schema.json
├── references/
│   ├── config-schema.md
│   ├── draft-v5.9.md
│   ├── benefit-images.md
│   ├── end-frame.md
│   └── permission-troubleshooting.md
└── tests/
```

`SKILL.md` 只保留触发条件、路由、授权边界和必要不变量；详细 Draft schema、配置和权限排障放在 references；重复且脆弱的 JSON 操作必须由确定性脚本完成。`derive_config.py` 只能辅助从参考工程生成候选配置，输出默认是 `draft` 状态，必须经人工复核改为 `approved` 才允许 apply。

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

建议一个入口、六个模式：

```text
python scripts/preprocess_draft.py validate-config --config-root <path> --config-set <id>
python scripts/preprocess_draft.py inspect         --draft <path>
python scripts/preprocess_draft.py plan            --job <job.json>
python scripts/preprocess_draft.py apply           --job <job.json>
python scripts/preprocess_draft.py validate        --draft <path> --job <job.json>
python scripts/preprocess_draft.py rollback        --draft <path> --run-id <id>
```

### `validate-config`

不打开、不修改 Draft。解析 bundle、组件 schema、配置集归属、短语冲突、`benefit_id` 引用和图片资产，输出组件 hash 与机器可读错误。CI 和 apply 都必须调用同一校验逻辑，不能维护两套规则。

### `inspect`

只读输出：

- Draft 版本和画布。
- 轨道、片段和素材统计。
- 视频 path 状态及 ffprobe 信息。
- dangling/duplicate IDs。
- 候选字幕轨和业务视频分段。
- 现有利益点图片、风险图层与尾帧候选，但不擅自认领其归属。
- 字体资源可用性。
- `draft_info.json` 与 `template-2.tmp` 的 hash 关系。
- `.jypre/state.json` 是否存在及其引用是否仍有效。

### `plan`

绝不写文件。输出：

- 输入文件 base SHA-256。
- 已选择的 `config_set_id` 和每个配置组件的 SHA-256。
- 利益点图片、风险提示和尾帧各自是 configured 还是 disabled。
- 目标视频解析结果和歧义。
- 将修改的 JSON path 白名单。
- 风险图新增、更新、冲突或 no-op 计划。
- 每个业务视频 segment 对应的尾帧区间、碰撞结果及末段策略。
- 字幕命中数量。
- 产品名和每条利益点的命中数量。
- 每条利益点图片规则命中的字幕、业务视频分段、目标帧区间和层级变更。
- 未命中、重叠、字体缺失和权限分类。
- 预计修改的 sidecar 与 Skill 状态文件。

### `apply`

- 要求目标工程未在剪映编辑页打开；首版可要求剪映完全关闭。
- 重新校验 base SHA 与全部配置 hash，避免 plan 后工程或配置被改动。
- 先备份将修改的文件。
- 在内存中生成全部目标文件。
- 写同目录临时文件、flush、fsync，再 `os.replace`。
- 多文件任一验证失败时自动 rollback。
- 配置校验、Draft 校验或尾帧碰撞任一失败时不执行部分应用。

### `validate`

除静态结构校验外，最终验收仍应在克隆 Draft 中打开剪映：

- 无红色离线/不支持媒体。
- 非空风险图透明且覆盖配置要求的区间；为空时没有 Skill 新增风险层。
- 字幕位置、缩放、换行正确。
- 产品名与利益点颜色/描边正确。
- 利益点图片只在同时命中配置利益点的字幕时段出现，位置、缩放、层级和入场动画正确。
- 非空尾帧在每个目标分段后准确持续 3 秒；为空时没有 Skill 新增尾帧层。
- 保存一次后结构仍闭合。
- 工程封面得到刷新。

## Job 配置

Job 只包含本次运行环境、配置集选择和严格程度，不包含业务内容：

```json
{
  "job_schema": 1,
  "draft_path": "/absolute/path/to/target-draft",
  "config_root": "/absolute/path/to/jianying-preprocessing/configs",
  "config_set": "taobao-flash-v1",
  "media_manifest": "/absolute/path/to/media-manifest.json",
  "search_roots": [],
  "media_strategy": "reference-existing",
  "permission_strategy": "diagnose-only",
  "subtitle_track": {
    "name": "字幕",
    "on_ambiguous": "fail"
  },
  "strict": {
    "unmatched_product": true,
    "unmatched_benefit": true,
    "unmatched_benefit_image": true,
    "font_missing": true,
    "unmanaged_layer_conflict": true
  }
}
```

Job schema 应显式拒绝旧式内联字段。想切换产品时只改 `config_set`，或者由上游选择另一个已经批准的 bundle。禁止通过 Job 临时覆盖某个组件；否则会重新引入“产品名来自 A、风险图来自 B”的混用风险。

## 事务与文件同步

可能修改的剪映文件：

- `draft_info.json`
- `draft_meta_info.json`
- `key_value.json`
- `draft_virtual_store.json`，可能原先不存在
- `template-2.tmp`，仅条件性同步

本 Skill 另行维护：

- `.jypre/state.json`
- `.jypre/backups/<run-id>/...`
- `.jypre/plans/<run-id>.json`

不应主动覆盖：

- `.backup/*`
- 剪映维护的历史 `.bak`
- `draft_cover.jpg`
- 未分类的二进制 `draft.extra`

当前三个样本中，`draft_info.json` 与各自的 `template-2.tmp` 分别完全同 hash。因此规则应为：

1. Plan 时记录两者 hash。
2. 如果 apply 前仍相等，则对 `template-2.tmp` 同步相同的 Draft 内容补丁。
3. 如果修改前不相等，默认不覆盖并报告冲突。

事务备份必须记录：

- 每个原文件的内容和 mode。
- 哪些目标文件原先不存在。
- 本次 run ID、Draft base hash、配置 hash 和计划白名单。
- 若做最小权限调整，记录旧 mode。
- 新建的 material、track、segment 和 sidecar ID，供 rollback 精确移除。

## 幂等性与配置切换

重复运行同一 Job 必须得到 no-op：

- 已连接到同一媒体内容时不重写 path。
- 已存在且状态映射、图片 hash、字幕来源和样式均相同的利益点图片片段时复用，不重复添加。
- 已存在相同托管风险图层时复用，不新增第二条。
- 每个源视频 segment 最多存在一个状态映射中的托管尾帧 segment。
- 字幕样式每次从语义规则重建，不在旧 styles 上继续叠加。
- Range 结果排序和序列化应确定性稳定。
- Sidecar ID 映射应从已存在记录复用，新增时使用稳定生成策略。
- `benefit_images=null`、`risk_warning=null` 或 `end_frame=null` 且不存在旧托管对象时是严格 no-op；存在可验证的旧托管对象时生成确定性删除计划。
- Apply 后再次执行 plan，不应产生待修改项。

利益点图片、风险图层和尾帧层不应仅依赖 track name 检测。识别时综合使用：

- `.jypre/state.json` 中的对象 ID 与来源映射。
- 配置的语义用途和组件 hash。
- 图片内容 hash。
- `type=photo`。
- 期望 timerange。
- 对利益点图片，还需核对来源字幕 segment ID、规则 ID、层级、clip 变换和动画资源。
- Draft 引用闭合关系。

配置切换必须生成“旧托管状态 → 新期望状态”的差异计划，不能在同一次 apply 中残留上一产品的高亮、利益点图片、风险图或尾帧。对于字幕富文本，始终从基础样式与新配置重新生成全量 ranges，而不是在旧 ranges 上做字符串替换。

## 校验清单

### 配置

- Catalog、Config Set 和全部非空组件通过各自 closed schema。
- 顶层 `config_set_id` 与 Catalog 一致，组件 `kind` 与配置槽位匹配。
- Config Set 为 approved；配置路径未逃逸配置根目录。
- Job 不包含任何业务内容覆盖字段。
- 产品名、利益点无跨类别重复或未声明重叠。
- 利益点图片仅引用同配置集内存在的 `benefit_id`，不重复存储 literal。
- 利益点图片、风险提示与尾帧的可空状态明确，不存在半空配置或空 `items` 伪关闭。
- 字幕样式配置声明固定720×1280画布，界面值为 `x=0`、`y=-500`、缩放250%、行间距5，并可确定性解析为已验证的 Draft 值。
- plan/apply 前后组件 hash 未变化。

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
- 利益点图片、风险图和尾帧 sidecar 映射闭合。
- `.jypre/state.json` 只指向实际存在且身份匹配的托管对象。

### 时间线

- 所有 timerange 非负。
- Draft duration 覆盖最大 segment end。
- 原业务视频和字幕时间线未改变。
- 利益点图片起止帧与其来源字幕占用帧区间相同；source/target raw duration 允许因帧边界取整相位相差1微秒。
- 非空风险图 segment 唯一并符合配置的覆盖区间。
- 非空尾帧数量等于选择器选中的源视频 segment 数量；末段不得跳过。
- 每个尾帧在当前30 fps草稿中准确为90帧；序列化 duration 为3000000微秒，并从对应原视频 segment 的结束帧开始。
- 尾帧不与下一业务视频、字幕或非托管内容碰撞。

### 媒体

- 文件存在、可 open。
- ffprobe 可解析业务视频。
- 候选媒体的宽高、音频、时长和 manifest 一致。
- 风险 PNG 具有 alpha；默认要求尺寸与画布一致。
- 利益点图片的 path、SHA-256、画布尺寸和 alpha 符合配置。
- 尾帧图片的 hash 和尺寸符合配置。
- 利益点图片、风险图与尾帧图没有发生 path/hash 错配。

### 字幕

- 字幕轨选择唯一。
- 预期的全部字幕 segment 命中。
- Material/segment 数量未意外改变。
- 字体路径存在且 resource ID 一致。
- 字幕布局写入值为 `transform=(0.0,-0.390625)`、`scale=(2.5,2.5)`，text material 的 `line_spacing=0.25`。
- 样式 ranges 连续、无重叠并覆盖全文。
- 产品名和利益点命中数量符合 strict 策略。
- 最终 ranges 的类别来源可追溯到具体配置文件、item ID 和 literal。
- 当前配置下每个业务视频分段恰好有一条同时命中两个指定 benefit ID 的字幕，并对应一个利益点图片 segment。

### 变更范围

- Semantic diff 只能落在 plan 的允许路径。
- 非目标轨道、片段 ID、时间范围和素材均保持不变。
- 配置为 `null` 时不得存在对应的 Skill 托管 material、track、segment 或 sidecar；配置切换产生的旧托管对象必须被事务化删除。
- 二次 plan 为 no-op。

## 首版非目标

- 不支持任意未知剪映版本。
- 不修改系统 TCC 数据库。
- 不通过复制 `com.apple.macl` 绕过授权。
- 不自行猜测、生成、改写产品名或利益点。
- 不根据文件名猜利益点图片、风险图或尾帧图的用途。
- 不通过 OCR 猜测利益点图片属于哪个利益点；绑定关系只能来自批准配置中的 `benefit_id`。
- 不允许 Job 内联覆盖已批准配置。
- 不重新识别、生成或调整字幕时间轴。
- 不自动平移视频、字幕、音频、变速或剪辑点来腾出尾帧空间。
- 不覆盖前置 Skill 未授权的其他工程。

## 实施顺序

建议按以下顺序开发：

1. 固化 Catalog、Config Set 与六类组件 JSON Schema 和 `validate-config`，先用错误 fixture 验证跨类别混用及悬空 benefit ID 会失败。
2. 将当前参考差异整理为首个 `taobao-flash-v1` 配置集，并人工批准。
3. `inspect`：实现完全只读的版本、引用、媒体、字幕及业务视频分段检查。
4. `plan`：实现确定性媒体解析、配置 hash 锁、高亮匹配及变更白名单。
5. 字幕样式与富文本 range patch。
6. 利益点图片及其动画、层级、逐字幕 timerange 和 sidecar patch，覆盖非空创建、`null` no-op 与托管删除测试。
7. 风险图及剪映 sidecar patch，覆盖 `null` no-op 与托管删除测试。
8. 尾帧 material/track/segment 规划与 patch，覆盖300帧空档、碰撞和末段延长 fixture。
9. `.jypre/state.json`、配置切换 reconciliation、原子事务、rollback 和幂等性。
10. POSIX 权限的最小修复分支。
11. 剪映原生 TCC/重连 UI 分支。
12. 在新的克隆工程中打开剪映做视觉验收。
13. 验证保存一次、关闭、重新打开后工程结构和视觉效果仍正确。

## 实现前需要确认的业务选择

### 已确认的新增业务规则

1. 尾帧开启时，末段空间不足必须延长工程 3 秒，以容纳完整尾帧。
2. 风险提示配置非空时，必须覆盖包括新增尾帧在内的最终工程时长。
3. 风险提示或尾帧切换为 `null` 时，必须删除此前由本 Skill 创建且可验证归属的对应对象。
4. 利益点图片允许为 `null`；切换为 `null` 时同样删除此前由本 Skill 创建且可验证归属的对应对象。
5. 首版画布固定为720×1280；字幕配置默认使用剪映界面位置 `x=0, y=-500`、缩放250%、行间距5。

### 仍需在实现前统一确认

1. 前置 Skill 是否保证传入的是可修改的工程副本。
2. 首版是否只支持剪映 5.9.0。
3. 风险提示图是否始终与画布同尺寸、透明并覆盖配置指定区间。
4. 未命中的产品名/利益点应警告还是整次失败；本文当前建议 approved 配置默认失败。
5. TCC 失败时是否允许自动打开剪映并通过原生文件选择器授权。
6. 是否允许将媒体 clone/copy 到 Draft staging 作为无人值守兜底。

## 当前建议

- 由前置 Skill 负责生成可修改的目标工程副本和精确媒体 manifest。
- 执行器只接受已批准的 `config_set_id`；不接受产品名、利益点、利益点图片、风险图或尾帧的自然语言临时指令。
- 当前淘宝闪购参考值成为首个 `taobao-flash-v1` 配置集，其中利益点图片和风险提示非空、尾帧为 `null`。
- 利益点图片、风险提示和尾帧的 `null` 必须是显式且可校验的功能关闭值；缺字段、空 `items` 或资产路径为空均失败。
- 本 Skill 默认在目标副本内事务化处理，并创建可回滚备份及托管状态。
- 首版锁定剪映 5.9.0 / Draft 360000 / 30 fps / 720×1280画布；其他帧率或画布只允许 inspect/plan，未验证前不得 apply。
- 先交付 schema、`validate-config`、inspect 和 plan，再开启 apply。
- 高亮只执行批准配置中的明确 literal/alias，不进行语义猜测。
- 利益点图片只通过已解析的 `benefit_id` 集合触发，跟随匹配字幕区间，并复现 Draft 3 中已验证的层级、变换和入场动画。
- 尾帧使用独立托管轨道、复用同一图片文件、每个源视频 segment 建一个3秒映射，不改变原视频和字幕时间线；在缺少尾帧参考 Draft 时不假定多个 segment 可以共享同一个 photo material 对象。
- 权限默认 diagnose-only；TCC 分支不宣称可以通过 chmod 修复。
- 最终完成条件必须包含一次剪映内的真实打开和视觉验收。
