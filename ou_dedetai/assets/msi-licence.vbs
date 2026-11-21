' Writes the licence agreement text from a Windows Installer package to a file.
' Run by cscript in the prefix: cscript //nologo msi-licence.vbs <package.msi> <output.txt>
' The text is the ScrollableText control on the installer's licence page (RTF, UTF-16).
Set installer = CreateObject("WindowsInstaller.Installer")
Set db = installer.OpenDatabase(WScript.Arguments(0), 0)
Set view = db.OpenView("SELECT `Text` FROM `Control` WHERE `Type`='ScrollableText'")
view.Execute
Set rec = view.Fetch
If Not rec Is Nothing Then
    Set fso = CreateObject("Scripting.FileSystemObject")
    Set f = fso.CreateTextFile(WScript.Arguments(1), True, True)
    f.Write rec.StringData(1)
    f.Close
End If
