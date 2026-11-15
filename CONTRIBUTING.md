# 贡献指南

感谢你愿意参与 Lotus Workbench。这个项目很小，规则也尽量少。

## 开始之前

- 先搜索 Issues，避免重复；功能类改动建议先开 issue 讨论
- 目标平台是 **Windows 11 + Python 3.12+**，不接受引入需要编译的重型依赖
- 设计红线：极简、不卡顿、键盘可用、不重复造轮子

## 本地开发

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt -r requirements-dev.txt
.venv\Scripts\python -m app
```

提交前自检：

```powershell
.venv\Scripts\python -m compileall app
.venv\Scripts\python tools\check_encoding.py
```

`check_encoding.py` 会检查中文文件是否被错误编码覆盖——本项目曾经踩过这个坑。

## 代码约定

- 4 空格缩进，行宽 100
- 模块内私有方法以 `_` 开头
- Qt 事件重写加 `# noqa: N802`
- 日志用 `logging.getLogger("lotus.<module>")`，不要 `print`
- 用户数据只能写到 `%USERPROFILE%\.lotus`，测试用 `LOTUS_HOME` 覆盖
- 不提交 `.venv`、`dist`、`.tmp`、日志和截图临时文件

## 提交信息

```
feat(bloom): 收纳盒支持自定义行列
fix(petal): 侧边栏滑出时不再遮挡收纳盒
docs: 补充材质实现说明
```

## 视觉改动

窗口材质、圆角、动画参数在 `app/ui/theme.py`、`app/ui/window_base.py`、`app/ui/glass.py`。
改动前请附截图（浅色 / 深色各一张），并说明是否影响性能。

## Pull Request

- 一个 PR 只做一件事
- 附上变更说明和验证方式
- 涉及 UI 的改动请贴截图
- CI 必须通过

## 许可证

提交即表示同意以 [MIT](LICENSE) 许可发布你的贡献。
