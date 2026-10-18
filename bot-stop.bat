@echo off
chcp 65001 >nul
schtasks /End /TN DigitalShopBot >nul && echo Бот остановлен. || echo Бот не был запущен.
timeout /t 3 >nul
