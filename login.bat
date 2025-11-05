echo off    

FOR /F "tokens=* USEBACKQ" %%F IN (`time /T`) DO (
SET my_time=%%F
)

set datecode=%date%-%my_time%
if "%1"=="s" echo %datecode% - Startup >> C:\Code\WorkTiming\login.txt
if "%1"=="i" echo %datecode% - Logged in >> C:\Code\WorkTiming\login.txt
if "%1"=="u" echo %datecode% - Unlocked >> C:\Code\WorkTiming\login.txt
if "%1"=="l" echo %datecode% - Locked >> C:\Code\WorkTiming\login.txt
if "%1"=="c" echo %datecode% - Connect >> C:\Code\WorkTiming\login.txt
if "%1"=="d" echo %datecode% - Disconnect >> C:\Code\WorkTiming\login.txt
