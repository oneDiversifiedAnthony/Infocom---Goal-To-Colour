@echo off
:: Launch.bat -- Double-click this to start World Cup Colour sACN
:: Launches the PowerShell script which self-elevates to Administrator.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch.ps1"
