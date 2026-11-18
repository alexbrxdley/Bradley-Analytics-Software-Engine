@echo off
title Bradley Analytics - alerts setup
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
  echo Node.js is not installed yet. Install it from nodejs.org ^(the LTS button^), restart the computer, then double-click this file again.
  pause
  exit /b
)
node worker\setup.mjs
echo.
pause
