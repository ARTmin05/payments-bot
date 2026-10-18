@echo off
chcp 65001 >nul
rem Показывает последние строки лога и следит за новыми (закрыть — Ctrl+C)
powershell -NoProfile -Command "Get-Content -LiteralPath '%~dp0bot.log' -Encoding UTF8 -Tail 30 -Wait"
