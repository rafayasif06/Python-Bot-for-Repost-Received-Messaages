@echo off
echo Creating virtual environment...
python -m venv venv

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing required packages...
pip install -r requirements.txt

echo Installing Playwright browsers...
python -m playwright install chromium

echo Setup complete!
echo To run the script, use the run.bat file
pause