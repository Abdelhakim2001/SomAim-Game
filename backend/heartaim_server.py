import asyncio, json
import numpy as np
import websockets
from collections import deque

HOST        = "0.0.0.0"
PORT        = 8765
SAMPLE_RATE = 100
BUFFER_SIZE = 500

ecg_buffer   = deque(maxlen=BUFFER_SIZE)
rr_intervals = deque(maxlen=300)
game_clients = set()

# Charger le modèle CNN
from heartaim_finetune import StressPredictor
predictor = StressPredictor('heartaim_stress_model.pt')
print("Modele CNN charge ✓")

# ── HRV ──────────────────────────────────────────────
def detect_rpeaks():
    import neurokit2 as nk
    if len(ecg_buffer) < BUFFER_SIZE:
        return
    sig = np.array(ecg_buffer)
    try:
        cleaned = nk.ecg_clean(sig, sampling_rate=SAMPLE_RATE)
        _, info  = nk.ecg_peaks(cleaned, sampling_rate=SAMPLE_RATE)
        peaks    = info["ECG_R_Peaks"]
        if len(peaks) >= 2:
            rr = np.diff(peaks) * (1000 / SAMPLE_RATE)
            rr_intervals.extend(rr[(rr > 300) & (rr < 1500)].tolist())
    except:
        pass

def compute_hrv_rmssd():
    if len(rr_intervals) < 5:
        return 0.0
    rr    = np.array(rr_intervals)
    rmssd = np.sqrt(np.mean(np.diff(rr) ** 2))
    return round(float(rmssd), 2)

# ── BROADCAST ────────────────────────────────────────
async def broadcast(data):
    if not game_clients:
        return
    msg  = json.dumps(data)
    dead = set()
    for c in game_clients:
        try:
            await c.send(msg)
        except:
            dead.add(c)
    game_clients -= dead

# ── HANDLER ESP32 ────────────────────────────────────
async def handle_esp(ws, path):
    print(f"[ESP32] Connecte: {ws.remote_address}")
    counter = 0
    try:
        async for msg in ws:
            d = json.loads(msg)

            if not d.get("connected"):
                print("Electrodes deconnectees")
                continue

            # Données reçues depuis ESP32
            ecg_value  = d.get("ecg", 0)
            bpm_esp    = d.get("bpm", 0)
            status_esp = d.get("heart_status", "Normal")  # High / Normal / Low

            ecg_buffer.append(ecg_value)
            counter += 1

            # Analyser toutes les 50 samples (0.5s)
            if counter % 50 == 0:
                detect_rpeaks()
                rmssd = compute_hrv_rmssd()

                # Prédiction CNN
                if len(ecg_buffer) >= BUFFER_SIZE:
                    result    = predictor.predict(list(ecg_buffer))
                    cnn_state = result['state']
                    cnn_conf  = result['confidence']
                else:
                    cnn_state = "NORMAL"
                    cnn_conf  = 0.0

                # Décision finale :
                # Priority 1 → BPM direct de l'ESP32
                # Priority 2 → CNN si BPM pas encore dispo
                if bpm_esp > 0:
                    heart_state = status_esp.upper()  # HIGH / NORMAL / LOW
                    speed_map   = {"HIGH": 1.0, "NORMAL": 0.6, "LOW": 0.2}
                    speed       = speed_map.get(heart_state, 0.6)
                else:
                    # Fallback CNN
                    heart_state = "HIGH" if cnn_state == "CALM" else "LOW" if cnn_state == "STRESS" else "NORMAL"
                    speed       = {"HIGH": 1.0, "NORMAL": 0.6, "LOW": 0.2}[heart_state]

                payload = {
                    "type":        "ecg_update",
                    "heart_state": heart_state,
                    "speed":       speed,
                    "hr":          round(bpm_esp),
                    "rmssd":       rmssd,
                    "cnn_state":   cnn_state,
                    "confidence":  cnn_conf
                }

                await broadcast(payload)
                print(f"BPM:{round(bpm_esp)} | RMSSD:{rmssd} | {heart_state} | speed:{speed} | CNN:{cnn_state}({cnn_conf})")

    except websockets.exceptions.ConnectionClosed:
        print("[ESP32] Deconnecte")

# ── HANDLER GAME ─────────────────────────────────────
async def handle_game(ws, path):
    print(f"[GAME] Connecte: {ws.remote_address}")
    game_clients.add(ws)
    await ws.send(json.dumps({
        "type":        "init",
        "heart_state": "NORMAL",
        "speed":       0.6,
        "hr":          0,
        "rmssd":       0.0,
        "cnn_state":   "NORMAL",
        "confidence":  0.0
    }))
    try:
        async for _ in ws:
            pass
    finally:
        game_clients.discard(ws)
        print("[GAME] Deconnecte")

# ── ROUTER ───────────────────────────────────────────
async def router(ws, path):
    if path == "/ecg":
        await handle_esp(ws, path)
    else:
        await handle_game(ws, path)

# ── MAIN ─────────────────────────────────────────────
async def main():
    print(f"HeartAim Server ws://{HOST}:{PORT}")
    print("ESP32 → ws://IP:8765/ecg")
    print("Game  → ws://IP:8765/game")
    async with websockets.serve(router, HOST, PORT):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())