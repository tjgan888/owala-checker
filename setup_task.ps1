# Register the background eslite check (needs admin). Runs at startup and every 10 minutes, logged in or not.
$dir = 'C:\Users\ganti\owala_eslite'
$py = 'C:\Users\ganti\AppData\Local\Programs\Python\Python314\python.exe'
$eslite = [string][char]0x8AA0 + [char]0x54C1
$log = "$dir\setup_task.log"
try {
    # S4U tasks may not load user env vars, so set NTFY_TOPIC inline; last run's output goes to last_run.log
    $cmd = "/c set NTFY_TOPIC=owala-24ksuj9mpq&& `"$py`" `"$dir\owala_stock.py`" --sites $eslite " +
           "--state `"$dir\local_state.json`" > `"$dir\last_run.log`" 2>&1"
    $act = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument $cmd -WorkingDirectory $dir
    $t1 = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 10)
    $t2 = New-ScheduledTaskTrigger -AtStartup
    $set = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew
    $pr = New-ScheduledTaskPrincipal -UserId 'timmygan\ganti' -LogonType S4U
    Register-ScheduledTask -TaskName 'Owala Eslite Check' -Action $act -Trigger $t1, $t2 -Settings $set `
        -Principal $pr -Force -ErrorAction Stop | Out-Null
    'OK' | Out-File $log
} catch {
    "FAIL: $($_.Exception.Message)" | Out-File $log
}
