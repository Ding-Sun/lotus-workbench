# 桌面挂件化 + 视图架构调研（2026-11-09）

> 内部笔记，用于 M4 重构前的方案对齐。本轮不改代码。

## 1. 参考图里读到的交互模型

两张截图（WitchDrawer、DeskBox）本质是同一类产品：**桌面收纳盒**。

- 盒子常驻桌面，随壁纸透出，不是呼出式面板。
- 头部极简：盒子名 + 条目数 + 溢出菜单；没有工具栏、没有关闭按钮。
- 折叠态是图标网格；展开/收起由点击或悬停触发，展开不是弹窗，而是盒子本身变高。
- 盒子可拖动、可吸附、可重叠；有的产品支持"分组"把多个盒子叠在一起用标签切换。
- 桌面右键可以新建盒子；盒子分两类：**移动型**（把文件移进盒子）和**映射型**（只存路径引用）。
- 设置面板里有：材质皮肤（清透雅致 / 暗黑曜石 / 全透水晶）、图标尺寸、透明度、展开方式（始终展开 / 点击展开 / 悬停自动展开）、开机自启。
- DeskBox 还带一个常驻底部 Dock 和若干桌面小组件（待办、天气）。

对 Lotus 的直接映射：

| 参考产品 | Lotus |
| --- | --- |
| 收纳盒 | Bloom 分组 |
| 待办盒 | Ink（M3 已具备） |
| 底部 Dock | Petal 可演进方向 |
| 材质/透明度设置 | 设置页（M6）第一批选项 |

结论：M4 的气泡框不该是"启动器"，而是"收纳盒 + 启动器"的混合体。折叠态负责好看，展开态负责好用。

## 2. Untamed 播放器：能核实的与推断的

### 2.1 本机能核实的事实

安装包 `C:\Program Files\WindowsApps\C19A3696...` 的结构：

- **WinUI 3 / Windows App SDK**：`Microsoft.UI.Xaml.dll`、`Microsoft.ui.xaml.dll`、`Microsoft.UI.Windowing.*`。
- **WinUIEx**（窗口与标题栏增强）、**CommunityToolkit.WinUI**（SettingsControls / Animations / Media / Converters / Triggers / Helpers）。
- **BASS 音频引擎**：`bass*.dll` + `BassAudioEngine.dll`。
- **WebView2**。
- 单文件主程序 `UntamedMusicPlayer.exe`（39 MB，ReadyToRun），XAML 以 XBF 编译进 `resources.pri`。

从 `resources.pri` 里提取出的页面清单（说明它是"Shell + 多页面"结构，而不是单窗口堆控件）：

```
ShellPage
HomePage
MusicLibraryPage
LocalSongsPage / LocalAlbumsPage / LocalArtistsPage
LocalAlbumDetailPage / LocalArtistDetailPage
OnlineSongsPage / OnlineAlbumsPage / OnlineArtistsPage / OnlinePlayListsPage
OnlineAlbumDetailPage / OnlineArtistDetailPage / OnlinePlayListDetailPage
PlayListDetailPage / PlayListsPage
PlayQueuePage / LyricPage
SettingsPage / Settings_LyricPage
```

模型层可见：`BriefLocalSongInfo`、`BriefUnknownSongInfo`、`IndexedPlaylistSong`、
`LocalAlbumInfo`、`LocalArtistInfo`、`PlaylistInfo`。另有 `ViewModels.SettingsViewModel`。

### 2.2 推断的视图架构

- `ShellPage` 承载 `NavigationView` + `Frame`，底部常驻播放条；切换页面只换 Frame 内容。
- 页面 = UserControl（XAML + code-behind 极少），逻辑在 ViewModel；数据用 `ObservableCollection` + `x:Bind`。
- 设置页用 CommunityToolkit 的 `SettingsCard`/`SettingsExpander` 拼装。
- 视觉上的"高级感"来自四件事，而不是某个控件：
  1. **分层材质**：Mica/Acrylic 打底 + 半透明卡片 + 1px 高光描边，三层叠出纵深。
  2. **大图与主导色**：专辑封面做大面积模糊背景，页面主色从封面提取。
  3. **克制的动效**：页面切换、列表项到详情的共享元素过渡（ConnectedAnimation）。
  4. **排版尺度**：固定的间距梯度（4/8/12/16/24）与字号梯度，不随意加粗放大。

### 2.3 能迁移到 Qt 的部分

| WinUI 做法 | Qt/PySide6 对应 |
| --- | --- |
| Shell + Frame 导航 | `QStackedWidget` + 自建 Page 基类 + 返回栈 |
| ObservableCollection + x:Bind | `QAbstractListModel` + `QSortFilterProxyModel`，`QListView` 虚拟化 |
| SettingsCard | 自建 `SettingRow(title, subtitle, control)` 复用组件 |
| Mica/Acrylic | 顶层窗口用 DWM 亚克力；桌面子窗口用"壁纸采样 + 缓存高斯模糊" |
| ConnectedAnimation | `QPropertyAnimation` 手写"共享元素"几何过渡 |
| Composition 隐式动画 | 只对 geometry / opacity 做属性动画，禁止逐帧布局 |
| ThemeResource | 已有 `Palette` dataclass，补齐间距与字号 token |

### 2.4 没做到的部分

GitHub（`github.com` / `raw.githubusercontent.com`）在本机网络解析到非公网地址，`web_fetch` 无法打开；
DeepWiki 返回 429、zread.ai 连接失败。所以**没有读到 Views 的源码**，以上是从安装包产物 + 通用
WinUI 3 模式推断的。若需要精读，最省事的办法是把仓库的 `UntamedMusicPlayer/Views` 目录
（以及 `ViewModels`、`Styles`）拷进工作区，我直接读文件。

## 3. 对 Lotus 的架构影响

### 3.1 视图层

- 新增 `Page` 基类：标题区（返回 + 标题 + 右侧操作）、内容区、统一内边距。
- Bloom 不再占满全屏、不再有遮罩与 Esc；它变成桌面层里的一个 `DesktopLayer`，内含若干卡片。
- Petal / Ink / Seek 仍是顶层窗口（需要压在其他窗口之上、需要 light dismiss）。
- 列表控件从"每次重建 QWidget"升级为 model/view；Bloom 单组 ≤16 项可暂缓，Seek 上百条必须换。

### 3.2 材质层

- 顶层窗口：DWM 亚克力 + 圆角区域裁剪（已实现）。
- 桌面卡片：**壁纸采样 + 模糊缓存**，卡片区域绘制模糊壁纸，外加 1px 高光描边和 8% 白色叠加。
- 卡片统一参数：圆角 16、描边 1px、内边距 14、图标 44、标题 8.5pt。

### 3.3 动效层

- 折叠 ↔ 展开：geometry 170ms `OutCubic`，内容在动画开始时切换、结束时不重排。
- 拖动吸附：松手后 120ms 归位，不做实时网格磁吸（省电、稳）。
- 页面切换：淡入 + 8px 上移 140ms。

## 4. 桌面挂载：结论与风险

本机现状（已探测）：

- `Progman` 直接挂着 `SHELLDLL_DefView`（图标层），不是经典"Progman + 图标 WorkerW"结构。
- 已存在 15 个 `WorkerW`，但都没有 `DefView`。

两条实现路线：

- **A（首选）**：向 `Progman` 发 `0x052C`，让 Explorer 重新分层，找到位于图标层下方的 `WorkerW`，
  `SetParent` 进去。层级最稳，Win+D 表现最接近参考产品。
- **B（兜底）**：`SetParent` 到 `Progman` + `SetWindowPos(HWND_BOTTOM)` + 隐藏 `SHELLDLL_DefView`。

必须先做**最小挂载试验**（纯色窗口，不碰数据、不隐藏图标），验证四件事：

1. 挂载后 `Win+D` 是否露出挂件；
2. 普通窗口（浏览器 / 编辑器）是否正常盖住它；
3. 鼠标点击是否正常落到挂件上，空白区是否穿透/接管；
4. Explorer 重启（`TaskbarCreated`）后是否还在。

已知代价：

- 子窗口没有 DWM 亚克力 → 自绘壁纸模糊；**动态壁纸 / 幻灯片会与卡片里的模糊不同步**。
- 隐藏原生图标是全局副作用：需要退出恢复、崩溃恢复、托盘手动恢复、Explorer 重启后重挂。
- `0x052C` 会改变 Explorer 的窗口层级，可能影响其他桌面小工具的挂载点，必须可逆。

## 5. 待办

- [ ] 最小挂载试验（需要用户授权操作桌面）
- [ ] Bloom 改 DesktopLayer + 卡片（自由坐标、双击打开、拖动吸附）
- [ ] 壁纸采样与模糊缓存
- [ ] 图标接管开关 + 恢复兜底
- [ ] 设置页：材质/透明度/展开方式/自启
- [ ] M5 Seek（es.exe 已就位：`D:\_Misc\Everything\ES-1.1.0.38.x64\es.exe`，暂缓）

## 6. 附：源码精读（2026-11-09 夜，已拿到仓库）

GitHub 直连仍不通，但 `codeload.github.com` / `api.github.com` 可用，已下载仓库并解包到
`.tmp/untamed-src`（342 个文件，不含 Assets/Libraries）。

### 6.1 壳层：ShellPage + MainWindow

- `MainWindow.xaml`：`WindowEx`（WinUIEx）根 Grid，`BackgroundGrid` 铺满、`Frame` 内容区、
  底部 117px 常驻 `RootPlayBarView`、右上 `InfoBar`。**播放条不属于任何页面**，切页不重建。
- `ShellPage.xaml`：`NavigationView` + `Frame`；48px 自绘标题栏；搜索框绑定 `Ctrl+E`；
  导航项各自挂 `KeyboardAccelerator`（`Ctrl+F` 主页、`Ctrl+R` 曲库、`Ctrl+Q` 队列、
  `Ctrl+Y` 歌单、`Ctrl+G` 设置）。
- 结论：**外层壳只负责"导航 + 常驻控件"，内容页只管自己的内容**。Lotus 的 Petal/Seek 可以照这个拆。

### 6.2 材质：MaterialSelectorService

- 可选 `Mica / MicaAlt / DesktopAcrylic(Default/Base/Thin) / Blur / Transparent / Animated`。
- 统一两个可调参数：`TintColor`（十六进制）与 `LuminosityOpacity`（0–100），
  改动经 **100ms 防抖** 才落到 controller。
- 失焦时把 `IsInputActive=false`，让亚克力退化成静态，省 GPU。
- 深/浅色各有一套 tint 常量（Mica 暗 `#202020`、亮 `#F3F3F3`；Acrylic 暗 `#2C2C2C`、亮 `#FCFCFC`）。
- `BlurredBackdrop` 用 `CompositionBrushBackdrop` + `CreateHostBackdropBrush()` 拿到**真·宿主背景模糊**。

对 Lotus 的意义：材质不是写死的，是"类型 + tint + 不透明度"三元组；我们的桌面挂件拿不到
DWM 亚克力，但可以复刻这套三元组，用"壁纸采样模糊"当 Blur 档。

### 6.3 动态背景：DynamicBackgroundService

- 从当前封面提取主色 → 生成线性渐变 → 两层 `SpriteVisual` 交叉淡入（800ms，新层到 0.5）。
- 颜色会先做 HSV 校正：饱和度保留，亮度压到 50%–90%，避免背景抢内容。

对 Lotus 的意义：气泡卡片的"主色"可以从图标提取，但没必要做动态渐变——我们的背景是壁纸，
卡片只需要 tint + 模糊。

### 6.4 设置页：SettingsCard / SettingsExpander

- 全部用 CommunityToolkit 的 `SettingsCard`（标题 + 描述 + 右侧控件）拼装，
  多条目用 `SettingsExpander`（可展开的子卡片列表）。
- 版式：`ScrollViewer` → `StackPanel Spacing=18` → 分组标题（BodyStrong）+ 卡片；
  页面左右边距 56（宽）/ 16（窄），由 `AdaptiveTrigger MinWindowWidth=641` 切换。
- 控件全是声明式绑定，code-behind 极薄。

对 Lotus 的意义：设置页不用自己设计版式，直接做 `SettingRow`：
`标题 13px/600 + 说明 11px/subtext + 右侧控件`，分组之间 18px，组内 2px。

### 6.5 响应式与列表

- `RootPlayBarView` 用三档 `VisualState`（0 / 641 / 861）在窄屏隐藏按钮、收到溢出菜单里；
- 曲库页用 `SelectorBar` 做"歌曲/专辑/艺术家"三段切换，切换只换 `Frame` 内容；
- 空状态有独立插画 + 主按钮；索引进度用底部 48px 亚克力条 + `ProgressRing`。

### 6.6 设计常量

- 间距：4 / 8 / 12 / 24 / 36（`Styles/Thickness.xaml` 里成体系）；
- 字号：仅自定义 24（大标题）与 16（中标题），其余走系统样式；
- 圆角：内容区 8、卡片 4–8，不滥用大圆角。

### 6.7 许可证提醒

仓库是 **AGPL-3.0**。Lotus 是 MIT：可以学习结构与交互模式，**不能复制其代码/资源**，
否则整个项目会被传染成 AGPL。上面所有结论都是"读结构、自己实现"。

### 6.8 可复用清单（给 Lotus 的落地项）

1. 壳层拆分：`Shell`（导航 + 常驻条）+ `Page`（纯内容）。
2. 材质三元组：`type + tint + opacity`，写进配置，桌面卡片用 Blur 档。
3. `SettingRow` 组件 + 18px 分组间距。
4. 三档响应式（窄/中/宽）用 `resizeEvent` 切 QSS 类，而不是堆媒体查询。
5. 键盘加速器集中注册（已有 HotkeyManager，可扩展成页内快捷键表）。

