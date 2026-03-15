' Double-click this to open the GUI with no terminal window at all.
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run "cmd /c cd /d """ & folder & """ && pip install -r requirements.txt -q 2>nul && pythonw tracker_gui.py", 0, False
