## Optional: Run on a RUG server (persistent) + access from your laptop

This section explains how to run the app on a University of Groningen Linux server so it keeps running even when your laptop is off.

It uses:
- `tmux` to keep processes running in the background
- an SSH tunnel to view the app in your local browser

---

### A) Connect to the server

```bash
ssh <s-number>@ssh.lwp.rug.nl
```

### B) Clone the repository on the server
```bash
mkdir -p ~/Desktop/¬/projects
cd ~/Desktop/¬/projects
git clone https://github.com/SenneHollard/library_reservation_manager.git
cd library_reservation_manager
```

### C) Create and activate a server virtual environment
```bash
python3 -m venv ~/venvs/libcal-ssh
source ~/venvs/libcal-ssh/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
playwright install chromium
```

### D) Start the Streamlit app in tmux
```bash
tmux new -s app
cd ~/Desktop/¬/projects/library_reservation_manager
source ~/venvs/libcal-ssh/bin/activate
VENV_PATH=$HOME/venvs/libcal-ssh bash run_app.sh
```
Detach (keep running in the background):
Press Ctrl + B, then press D

### E) Access the app from your own laptop (SSH tunnel)
On your laptop:
```bash
ssh -N -L 8765:127.0.0.1:8765 <s-number>@ssh.lwp.rug.nl
```
Open in your browser:
http://localhost:8765

### F) Start the worker in tmux (optional)
```bash
tmux new -s workers
cd ~/Desktop/¬/projects/library_reservation_manager
source ~/venvs/libcal-ssh/bin/activate
VENV_PATH=$HOME/venvs/libcal-ssh bash run_worker.sh
```
Detach:
Press Ctrl + B, then press D

### G) Useful tmux commands
List running sessions:
```bash
tmux ls
```

Attach to a session:
```bash
tmux attach -t app
tmux attach -t workers
```