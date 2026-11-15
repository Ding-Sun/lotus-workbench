# 安全说明

Lotus Workbench 是一个本地桌面程序，不联网、不上传数据。

## 本地数据

- 配置、笔记、日志：`%USERPROFILE%\.lotus`
- 崩溃记录：`%USERPROFILE%\.lotus\logs\crash.log`
- 程序不会把任何数据发送到外部服务

## 权限

- 默认以当前用户权限运行，**不需要管理员**
- 「隐藏桌面图标」通过 Explorer 自己的命令切换，不是提权操作
- 「管理员 PS」终端按钮会触发 UAC，这是 Windows 的行为

## 报告漏洞

如果发现安全问题（例如路径穿越、任意代码执行、配置文件注入），请不要公开开 issue，直接通过 GitHub 的
[Private vulnerability reporting](https://github.com/Ding-Sun/lotus-workbench/security/advisories/new) 提交。

一般问题请走 Issues。
