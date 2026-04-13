# Battleship  
Author: Mila Zhang (22756463)

Demo: https://youtu.be/48L8GeLMMas

## Platform Compatibility

This project has been thoroughly tested on **macOS**, where all features described in the report and demo function as expected.

> ⚠️ **Note for Windows Users**  
> Some features may not work as intended on Windows. Specifically, the **Client ID** feature behaves differently:  
> - On **macOS**: The Client ID is automatically generated based on the terminal device name.  
> - On **Windows**: Users must manually input a **3-digit ID** to enable client identification and reconnection support.

---

## Setup Instructions
### Create Conda Environment
Run `conda create --name new_env_name --file requirements.txt` to install the package. Alternatively, run `conda env create -f environment.yaml` to recreate the environment.

### Running the Game
1. After changing into the project directory, simply run `python server.py` to start the server. 
2. Then open a new terminal, change into the project directory and run `python client.py` to create a new client. 
3. Repeat step 2 to create multiple clients.
