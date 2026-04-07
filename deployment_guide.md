# NexLab LIS Deployment Guide (Server PC)

This guide helps you move the NexLab Laboratory System to a new PC and set it up as a server for other machines in the lab.

## Step 1: Copying the System
1. Locate the `NexLab_Published` folder created by the packager.
2. Copy this entire folder to your target PC (e.g., using a USB Drive).
3. Place it in a safe location (e.g., `C:\NexLab_LIS`).

## Step 2: One-Time Set Up (Target PC)
1. Open the `NexLab_Published` folder on the new PC.
2. Double-click `install_requirements.bat`. This will:
   - Create the virtual environment.
   - Install all Python libraries.
   - Download the PDF generation components (Playwright Chrome).
   - *Note: This requires internet access the first time.*

## Step 3: Running the System
1. Double-click `start_nexlab.bat`.
2. A window will open showing that the server is running.
3. You can access the system on this PC at: `http://localhost:8000` (or your chosen port).

## Extra: How to Change the Port
If you need to change the port (e.g. to 5000 or 80):
1.  Open `start_nexlab.bat` in Notepad.
2.  Change the line `set "PORT=8000"` to your preferred number.
3.  Save the file and restart the system.

## Step 4: Connecting from Other PCs
1. find the **IP Address** of the Server PC:
   - Open Command Prompt and type `ipconfig`.
   - Look for "IPv4 Address" (e.g., `192.168.1.50`).
2. On any other PC in the lab, open a browser and go to: `http://192.168.1.50:8000`.

## Step 5: (Optional) Automatic Start
1. To make the server start automatically when you log into Windows:
2. Double-click `add_to_startup.bat` once.

---
### Requirements for the Server PC:
- Windows 10/11.
- Python 3.10 or higher installed (one-time requirement for the environment setup).
- Port 8000 allowed in Windows Firewall (if connecting from other PCs).
