Option Explicit
Dim shell, fs, root, python, command
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
root = fs.GetParentFolderName(WScript.ScriptFullName)
python = fs.BuildPath(root, ".venv\Scripts\python.exe")
command = Chr(34) & python & Chr(34) & " " & Chr(34) & fs.BuildPath(root, "launch.py") & Chr(34) & " --watcher --stop"
On Error Resume Next
shell.Run command, 0, False
If Err.Number <> 0 Then MsgBox "Cannot stop watcher. Check the project Python installation.", 16, "GPT Desktop Pet Watcher"
