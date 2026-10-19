Option Explicit
Dim shell, fs, root, python, command, result
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
root = fs.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = root
python = fs.BuildPath(root, ".venv\Scripts\python.exe")
If fs.FileExists(python) Then
    command = Chr(34) & python & Chr(34)
Else
    command = "py -3"
End If
command = command & " " & Chr(34) & fs.BuildPath(root, "launch.py") & Chr(34) & " --watcher"
On Error Resume Next
result = shell.Run(command, 0, False)
If Err.Number <> 0 Then
    MsgBox "Cannot start Python. Please follow README.md to install requirements.txt in .venv.", 16, "GPT Desktop Pet Watcher"
End If
