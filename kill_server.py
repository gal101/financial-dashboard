import psutil
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        if p.info['name'] in ('python.exe', 'python', 'pythonw.exe'):
            cmdline = p.info['cmdline']
            if cmdline and any('server.py' in arg for arg in cmdline) and not any('kill_server.py' in arg for arg in cmdline):
                print(f"Killing PID {p.info['pid']}: {cmdline}")
                p.terminate()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
