@echo off
REM ============================================================
REM  Rotating PM Magnet — Full Pipeline
REM  1. Generate mesh (if not already done)
REM  2. Convert to Elmer format
REM  3. Generate 36 angle SIF files
REM  4. Solve all 36 angles
REM  5. Generate PVD for ParaView animation
REM ============================================================
setlocal

REM -- Paths --------------------------------------------------------
set ELMER_HOME=D:\Elmer\Elmer 9.0-Release
set PATH=%ELMER_HOME%\bin;%ELMER_HOME%\lib\elmersolver;%ELMER_HOME%\stripped_gfortran\bin;%PATH%

cd /d "%~dp0"

echo.
echo ============================================================
echo  Rotating PM Magnet — 5 Hz (300 RPM), 36 angles
echo ============================================================
echo.

REM -- 1. Generate mesh (skip if mesh.msh exists) -------------------
if not exist "mesh.msh" (
    echo [1/4] Generating Gmsh mesh...
    python magnet_mesh.py
    if %ERRORLEVEL% NEQ 0 (
        echo ERROR: Mesh generation failed!
        pause & exit /b 1
    )
) else (
    echo [1/4] Mesh already exists — skipping.
)

REM -- 2. Convert to Elmer format -----------------------------------
echo [2/4] Converting mesh to Elmer format...
if not exist "mesh\mesh.header" (
    ElmerGrid 14 2 mesh.msh -out mesh -autoclean
    if %ERRORLEVEL% NEQ 0 (
        echo ERROR: ElmerGrid conversion failed!
        pause & exit /b 1
    )
) else (
    echo [2/4] Elmer mesh already converted — skipping.
)

REM -- 3. Generate 36 SIF files --------------------------------------
echo [3/4] Generating 36 SIF files for rotation scan...
python rotate_scan.py
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: SIF generation failed!
    pause & exit /b 1
)

REM -- 4. Run all 36 solves -----------------------------------------
echo [4/4] Running all 36 solves...
cd mesh
call run_all_angles.bat
cd ..

REM -- 5. Generate PVD ----------------------------------------------
echo.
echo Generating ParaView PVD animation file...
python create_pvd.py

echo.
echo ============================================================
echo  Done! Open rotate_animation.pvd in ParaView.
echo  Use Clip + Glyph to visualize the rotating B field.
echo ============================================================
pause
endlocal
