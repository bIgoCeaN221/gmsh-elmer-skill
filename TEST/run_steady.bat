@echo off
REM ============================================================
REM  Run Elmer steady-state simulation for the rotating magnet
REM  Double-click this file or run from Command Prompt.
REM ============================================================
setlocal

REM -- Elmer paths -------------------------------------------------
set ELMER_HOME=D:\Elmer\Elmer 9.0-Release
set PATH=%ELMER_HOME%\bin;%ELMER_HOME%\lib\elmersolver;%ELMER_HOME%\stripped_gfortran\bin;%PATH%

REM -- Work in the mesh directory ----------------------------------
cd /d "%~dp0mesh2"

REM -- Copy latest SIF ---------------------------------------------
copy /Y "..\case_steady.sif" "case_steady.sif" > NUL

echo.
echo ============================================================
echo  Elmer steady-state: radial PM magnet
echo  Mesh: %~dp0mesh
echo ============================================================
echo.

REM -- Run solver ---------------------------------------------------
ElmerSolver.exe case_steady.sif
set ELMER_EXIT=%ERRORLEVEL%

echo.
echo ============================================================
echo  ElmerSolver exit code: %ELMER_EXIT%
echo  Check results\  directory for VTU output files.
echo  Open results\case*.vtu in ParaView.
echo ============================================================

pause
endlocal
exit /b %ELMER_EXIT%
