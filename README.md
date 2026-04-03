# HeartAim — ECG Biofeedback Aim Trainer

Jeu de précision contrôlé par le rythme cardiaque via ESP32 + AD8232.

## Prérequis
- Mac / Linux / Windows
- Python 3.10
- Miniconda ou Anaconda
- Arduino IDE (pour flasher l'ESP32)
- ESP32 + capteur AD8232

## Installation

### 1. Cloner le projet
git clone https://github.com/Abdelhakim2001/SomAim-Game.git
cd SomAim-Game

### 2. Créer l'environnement conda
conda create -n heartaim python=3.10
conda activate heartaim

### 3. Installer les dépendances
pip install torch torchvision torchaudio
pip install websockets neurokit2 numpy scipy pandas
pip install scikit-learn pygame

### 4. Entraîner le modèle (une seule fois)
cd backend
python heartaim_finetune.py

## Lancer le projet

### Terminal 1 — Serveur
conda activate heartaim
cd backend
python heartaim_server.py

### Terminal 2 — Jeu
conda activate heartaim
cd game
python heartaim_game.py

## Configuration ESP32
1. Trouver ton IP : ipconfig getifaddr en0
2. Modifier heartaim_esp32.ino :
   const char* SSID     = "TON_WIFI";
   const char* PASSWORD = "TON_PASSWORD";
   const char* WS_HOST  = "TON_IP";
3. Arduino IDE → Upload

## Branchement AD8232
AD8232 → ESP32
3.3V   → 3.3V
GND    → GND
OUTPUT → PIN 34
LO+    → PIN 32
LO-    → PIN 33

## Sans ESP32 (mode demo)
python heartaim_game.py
