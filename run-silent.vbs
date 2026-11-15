' Launch Lotus Workbench without a console window.
' Uses the project's virtualenv pythonw.exe so the same interpreter and
' packages as run.bat are used; errors are written to crash.log by the app.
Option Explicit

Dim shell, fso, root, pythonw, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

root = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = root & "\.venv\Scripts\pythonw.exe"

If Not fso.FileExists(pythonw) Then
    MsgBox "找不到 " & pythonw & vbCrLf & "请先创建虚拟环境并安装依赖。", vbCritical, "Lotus Workbench"
    WScript.Quit 1
End If

shell.CurrentDirectory = root
cmd = """" & pythonw & """ -m app"
' 0 = hidden window, False = do not wait
shell.Run cmd, 0, False
