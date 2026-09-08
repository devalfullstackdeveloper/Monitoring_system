Option Explicit

Dim shell, fso, root, q
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
q = Chr(34)

Dim backendPython, agentPython
backendPython = root & "\backend\venv\Scripts\python.exe"
agentPython = root & "\desktop-agent\venv\Scripts\pythonw.exe"

If (Not PythonWorks(backendPython)) Or (Not PythonWorks(agentPython)) Then
    MsgBox "Org Tracker can't start: the backend and/or desktop-agent virtual " & _
           "environment is missing or broken on this computer." & vbCrLf & vbCrLf & _
           "This usually happens when the project folder (including its 'venv' " & _
           "subfolders) was copied from a different computer - Python virtual " & _
           "environments only work on the machine that created them." & vbCrLf & vbCrLf & _
           "Fix: run setup.bat once in this project folder, then try again.", _
           vbCritical, "Org Tracker - Setup needed"
    WScript.Quit 1
End If

If Not BackendIsRunning() Then
    StartHidden "cmd.exe /c cd /d " & q & root & "\backend" & q & " && " & q & backendPython & q & " -m uvicorn app.main:app --reload --host 0.0.0.0 --port " & GetBackendPort()
End If
If Not BackendReady() Then
    MsgBox "Org Tracker can't start because the backend did not become ready." & vbCrLf & vbCrLf & _
           "Check PostgreSQL is running, then try again.", _
           vbCritical, "Org Tracker - Backend unavailable"
    WScript.Quit 1
End If
If Not FrontendIsRunning() Then
    StartHidden "cmd.exe /c cd /d " & q & root & "\frontend" & q & " && npm.cmd run dev"
End If
If Not AgentIsRunning() Then
    StartHidden "cmd.exe /c cd /d " & q & root & "\desktop-agent" & q & " && " & q & agentPython & q & " agent.py"
End If

Sub StartHidden(command)
    shell.Run command, 0, False
End Sub

Function AgentIsRunning()
    Dim service, processes, process
    AgentIsRunning = False
    On Error Resume Next
    Set service = GetObject("winmgmts:\\.\root\cimv2")
    Set processes = service.ExecQuery("SELECT Name, CommandLine FROM Win32_Process")
    For Each process In processes
        If LCase(process.Name) = "pythonw.exe" Or LCase(process.Name) = "python.exe" Then
            If InStr(1, process.CommandLine, root & "\desktop-agent", vbTextCompare) > 0 And _
               InStr(1, process.CommandLine, "agent.py", vbTextCompare) > 0 Then
                AgentIsRunning = True
                Exit For
            End If
        End If
    Next
    On Error GoTo 0
End Function

Function GetBackendPort()
    ' Reads PORT= from backend\.env so this can never drift out of sync
    ' with what desktop-agent\.env / frontend\.env expect - the port is
    ' only ever set in one place (backend\.env), never hardcoded here.
    Dim envPath, f, line, port
    port = "8000"
    envPath = root & "\backend\.env"
    If fso.FileExists(envPath) Then
        Set f = fso.OpenTextFile(envPath, 1)
        Do While Not f.AtEndOfStream
            line = Trim(f.ReadLine)
            If LCase(Left(line, 5)) = "port=" Then
                port = Mid(line, 6)
            End If
        Loop
        f.Close
    End If
    GetBackendPort = port
End Function

Function PythonWorks(pyPath)
    Dim wshExec, tries
    PythonWorks = False

    If Not fso.FileExists(pyPath) Then
        Exit Function
    End If

    On Error Resume Next
    Set wshExec = shell.Exec(q & pyPath & q & " --version")
    If Err.Number <> 0 Then
        Err.Clear
        Exit Function
    End If
    On Error Goto 0

    tries = 0
    Do While wshExec.Status = 0 And tries < 100
        WScript.Sleep 50
        tries = tries + 1
    Loop

    If wshExec.Status = 1 And wshExec.ExitCode = 0 Then
        PythonWorks = True
    End If
End Function

Function BackendIsRunning()
    BackendIsRunning = ProcessCommandContains("uvicorn app.main:app")
End Function

Function BackendReady()
    Dim request, tries, url
    BackendReady = False
    url = "http://127.0.0.1:" & GetBackendPort() & "/health"
    For tries = 1 To 30
        On Error Resume Next
        Set request = CreateObject("MSXML2.XMLHTTP")
        request.Open "GET", url, False
        request.Send
        If Err.Number = 0 And request.Status = 200 Then
            BackendReady = True
            On Error GoTo 0
            Exit Function
        End If
        Err.Clear
        On Error GoTo 0
        WScript.Sleep 500
    Next
End Function

Function FrontendIsRunning()
    FrontendIsRunning = ProcessCommandContains(root & "\frontend") And _
                        ProcessCommandContains("run dev")
End Function

Function ProcessCommandContains(text)
    Dim service, processes, process
    ProcessCommandContains = False
    On Error Resume Next
    Set service = GetObject("winmgmts:\\.\root\cimv2")
    Set processes = service.ExecQuery("SELECT CommandLine FROM Win32_Process")
    For Each process In processes
        If InStr(1, process.CommandLine, text, vbTextCompare) > 0 Then
            ProcessCommandContains = True
            Exit For
        End If
    Next
    On Error GoTo 0
End Function