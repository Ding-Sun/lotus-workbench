# 架构说明

这份文档记录「为什么这样做」，比代码更容易过时，改动实现时请顺手更新。

## 模块

```
app/
├── main.py            启动流程：单实例 → 日志 → 配置/主题 → 窗口 → 托盘/热键 → 桌面层
├── core/
│   ├── bloom.py       收纳盒数据模型（BloomGroup / BloomItem）与读写
│   ├── config.py      JSON 配置，点路径访问 + 版本迁移
│   ├── desktop_icons.py  桌面图标显隐（三级兜底）
│   ├── hotkeys.py     RegisterHotKey + WM_HOTKEY 原生事件过滤
│   ├── launcher.py    启动程序 / 打开路径 / 终端进程注册表
│   ├── logger.py      文件日志（失败时退到临时目录）
│   ├── notes.py       速记存储（纯文本 + 元数据）
│   ├── single_instance.py  QLockFile 单实例 + 消息转发
│   └── wallpaper.py   壁纸主色提取
└── ui/
    ├── window_base.py 所有窗口的基类：无边框 + 磨砂 + 圆角 + 淡入滑动
    ├── glass.py       截屏模糊与材质合成
    ├── desktop.py     收纳盒窗口与桌面层管理
    ├── petal.py       侧边栏 + 热区
    ├── ink.py         速记编辑 / 笔记管理
    ├── settings.py    设置中心
    ├── materials.py   材质预设
    ├── theme.py       调色板与配色决策
    ├── rows.py        键盘可操作的列表控件
    └── icons.py       程序图标生成
```

## 启动顺序

顺序是刻意的：

1. `ensure_dirs()` —— 目录不存在时日志会失败
2. `QApplication` —— 单实例锁依赖 Qt
3. `SingleInstance.acquire()` —— **在写日志之前**拿锁，避免两个进程抢 `lotus.log`
4. 日志 → 配置 → 主题
5. 窗口、托盘、热键、桌面层
6. `DesktopLayer.build()`

第二个实例拿不到锁时，会通过本地 socket 通知第一个实例，并弹一个说明框。

## 桌面层与 z-order

收纳盒不是桌面子窗口。原因：在这台机器上 `SetParent(Progman)`、`CreateWindowEx(parent=Progman)`、`SetWindowLongPtr(GWLP_HWNDPARENT)` 全部失败（`err=5`/`err=87`），即使提权到 Medium 也一样。

实际做法：

- 每个收纳盒是独立的 `WS_EX_NOACTIVATE` 工具窗口
- `bed_at_bottom()` 把窗口插到 `Progman` 上方那个 z-order 槽位（`GetWindow(progman, GW_HWNDPREV)`）
- 900ms 看门狗在窗口被隐藏 / 最小化（`Win+D`）后重新展示并置底
- 侧边栏滑出时，气泡整体左移一个侧边栏宽度避让

## 磨砂窗口

Windows 提供的两条路都验证过：

- `SetWindowCompositionAttribute(ACCENT_ENABLE_ACRYLICBLURBEHIND)`：返回成功，画面无变化
- `DwmSetWindowAttribute(DWMWA_SYSTEMBACKDROP_TYPE)`：返回成功，客户区全黑

因此 `glass.py` 自己实现：窗口显示前截取将占据的屏幕区域 → 缩到 1/4 → `QGraphicsBlurEffect` → 放大回原尺寸 → 叠材质色。窗口尺寸变化时按新尺寸缩放旧底图重新合成。

代价是快照语义：移动窗口、换壁纸后底图不会自动更新。

## 配置

`%USERPROFILE%\.lotus\config.json`。`config.py` 里有 `DEFAULTS` 和 `CONFIG_VERSION`，`_read()` 时做深合并并按版本迁移（例如 v2 把强调色切到壁纸取色，v3 引入材质预设）。

所有 UI 改动都只通过 `cfg.set("a.b.c", value)` 落盘，不做第二套设置存储。

## 线程与性能

- 没有后台线程；所有 IO 都是小文件读写
- 不做文件系统轮询，不监听目录
- 列表按需构建，图标用缓存（`_icon_cache`）
- 模糊只发生在窗口打开/尺寸变化时，且在半分辨率下进行

## 桌面图标显隐

`desktop_icons.py` 按优先级尝试：

1. 向 `SHELLDLL_DefView` 发送 `WM_COMMAND`（`0x7402`，即右键菜单「显示桌面图标」）
2. 发给它的父窗口（Progman / WorkerW）
3. 写 `HKCU\...\Explorer\Advanced\HideIcons` 并广播 `WM_SETTINGCHANGE`

**不要**直接 `ShowWindow(DefView, SW_HIDE)`：在部分 Windows 11 构建上会连壁纸一起隐藏，桌面变黑。
