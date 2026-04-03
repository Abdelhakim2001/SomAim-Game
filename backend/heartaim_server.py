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

# Charger le modèle CNN entraîné
from heartaim_finetune import StressPredictor
predictor = StressPredictor('heartaim_stress_model.pt')
print("Modele CNN charge ✓")

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

def compute_hr():
    if len(rr_intervals) < 2:
        return 0
    return round(60000 / np.mean(list(rr_intervals)[-10:]))

def compute_hrv_rmssd():
    if len(rr_intervals) < 5:
        return 0
    rr    = np.array(rr_intervals)
    rmssd = np.sqrt(np.mean(np.diff(rr) ** 2))
    return round(float(rmssd), 2)

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

async def handle_esp(ws, path):
    print(f"[ESP32] Connecte: {ws.remote_address}")
    counter = 0
    try:
        async for msg in ws:
            d = json.loads(msg)
            if not d.get("connected"):
                continue

            ecg_buffer.append(d["ecg"])
            counter += 1

            # Analyser toutes les 50 samples (0.5 seconde)
            if counter % 50 == 0:
                detect_rpeaks()

                hr    = compute_hr()
                rmssd = compute_hrv_rmssd()

                # Prédiction CNN sur le signal brut
                if len(ecg_buffer) >= BUFFER_SIZE:
                    result = predictor.predict(list(ecg_buffer))
                    state  = result['state']   # CALM ou STRESS
                    conf   = result['confidence']
                else:
                    state = "NORMAL"
                    conf  = 0.0

                # Mapper vers HIGH / NORMAL / LOW
                # basé sur HR + HRV + CNN
                if hr > 0:
                    if hr < 65 and rmssd > 40:
                        heart_state = "HIGH"    # calme, HRV élevé
                        speed = 1.0
                    elif hr > 90 or rmssd < 15:
                        heart_state = "LOW"     # stressé, HRV faible
                        speed = 0.2
                    else:
                        heart_state = "NORMAL"
                        speed = 0.6
                else:
                    # Fallback sur CNN seul
                    heart_state = "HIGH" if state == "CALM" else "LOW" if state == "STRESS" else "NORMAL"
                    speed = {'HIGH': 1.0, 'NORMAL': 0.6, 'LOW': 0.2}[heart_state]

                payload = {
                    "type":        "ecg_update",
                    "heart_state": heart_state,  # HIGH / NORMAL / LOW
                    "speed":       speed,
                    "hr":          hr,
                    "rmssd":       rmssd,
                    "cnn_state":   state,
                    "confidence":  conf
                }

                await broadcast(payload)
                print(f"HR:{hr}bpm | RMSSD:{rmssd}ms | {heart_state} | speed:{speed} | CNN:{state}({conf})")

    except websockets.exceptions.ConnectionClosed:
        print("[ESP32] Deconnecte")

async def handle_game(ws, path):
    print(f"[GAME] Connecte: {ws.remote_address}")
    game_clients.add(ws)
    await ws.send(json.dumps({
        "type": "init", "heart_state": "NORMAL",
        "speed": 0.6, "hr": 0, "rmssd": 0
    }))
    try:
        async for _ in ws:
            pass
    finally:
        game_clients.discard(ws)

async def router(ws, path):
    if path == "/ecg":
        await handle_esp(ws, path)
    else:
        await handle_game(ws, path)

async def main():
    print(f"HeartAim Server ws://{HOST}:{PORT}")
    async with websockets.serve(router, HOST, PORT):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())