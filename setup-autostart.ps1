# Регистрирует бота в Планировщике заданий Windows:
# запуск в фоне (без окна) при входе в систему и перезапуск при падении.
# Удалить: Unregister-ScheduledTask -TaskName DigitalShopBot -Confirm:$false

$TaskName = "DigitalShopBot"
$Dir = $PSScriptRoot
$Pythonw = Join-Path $Dir ".venv\Scripts\pythonw.exe"

$action = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$Dir\bot.py`"" -WorkingDirectory $Dir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Telegram-бот с оплатой Digital Shop (портфолио)" -Force | Out-Null

Write-Host "Задача $TaskName зарегистрирована."
