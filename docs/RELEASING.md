# 发布流程

## 版本号

`app/__init__.py` 里的 `__version__` 是唯一来源：设置窗口、`--version`、打包产物都读它。

- 修 bug：`0.5.1`
- 加功能：`0.6.0`
- 破坏性改动：`1.0.0`

## 发版步骤

1. 改 `__version__`，同步 `README.md` 徽章、`CHANGELOG.md`
2. 本地验证：
   ```powershell
   .venv\Scripts\python -m compileall app
   .venv\Scripts\python tools\check_encoding.py
   .venv\Scripts\pyinstaller --noconfirm Lotus.spec
   ```
3. 提交并打 tag：
   ```powershell
   git add -A
   git commit -m "release: v0.5.0"
   git tag v0.5.0
   git push origin main --tags
   ```
4. CI 会构建并生成 `Lotus-Workbench-v0.5.0.zip`，附到 Release 草稿
5. 在 GitHub 上编辑 Release 说明，直接粘贴 `RELEASE_NOTES_v0.5.0.md` 的内容
6. 上传本地打包的资产（可选）：
   ```powershell
   Compress-Archive -Path dist\Lotus\* -DestinationPath Lotus-Workbench-v0.5.0-win64.zip
   Get-FileHash Lotus-Workbench-v0.5.0-win64.zip -Algorithm SHA256
   ```
   把 SHA256 写进 Release 说明的「校验」一节。

## Release 说明怎么写

- 第一段说清楚「这个版本是什么、解决什么问题」
- 按模块列亮点，别贴 commit 列表
- 必须写：下载方式、系统要求、已知问题
- 大版本附截图
- 告诉用户去哪反馈

模板见仓库根目录的 `RELEASE_NOTES_v<version>.md`。

## 资产命名

```
Lotus-Workbench-v0.5.0-win64.zip     # onedir 打包
Lotus-Workbench-v0.5.0-source.zip    # GitHub 自动生成，不用手动传
```
