## Local installation & usage

This guide explains how to run the project locally on your own machine
(Mac or Linux).

### 1. Clone the repository

```bash
git clone https://github.com/SenneHollard/library_reservation_manager.git
cd library_reservation_manager
```

### 2. Create and activate a virtual environment

```bash
mkdir -p ~/venvs
python3 -m venv ~/venvs/libcal
source ~/venvs/libcal/bin/activate
```

### 3. Install Python dependencies

```bash
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

### 4. Install Playwright browser (one-time)

```bash
playwright install chromium
```

### 5. Run the Streamlit application

```bash
bash run_app.sh
```

The app will be available at:

http://127.0.0.1:8765

If port 8765 is already in use on your machine, you can run the app on a different port by setting the `PORT` environment variable, for example:

```bash
PORT=9000 bash run_app.sh
```

### 6. Run background workers (optional)

In a second terminal window:

```bash
source ~/venvs/libcal/bin/activate
bash run_worker.sh
```

You can check or stop the worker with:

```bash
bash worker_status.sh
bash stop_worker.sh
```

### Notes

If you use a different virtual environment path, you can override it when running scripts:

```bash
VENV_PATH=/path/to/venv bash run_app.sh
```
