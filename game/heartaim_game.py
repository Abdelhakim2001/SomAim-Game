# pip install pygame websockets
import pygame, math, random, threading, asyncio, json, websockets

W, H    = 1280, 720
FPS     = 60
WS_URL  = "ws://localhost:8765/game"

# Couleurs
BG      = (10, 10, 15)
GRID    = (26, 26, 46)
WHITE   = (224, 224, 224)
GREEN   = (46, 204, 113)
BLUE    = (52, 152, 219)
RED     = (231, 76, 60)
ORANGE  = (243, 156, 18)
PURPLE  = (155, 89, 182)
CYAN    = (0, 212, 255)

# State reçu depuis ESP32 via serveur
ecg_state = {
    "heart_state": "NORMAL",  # HIGH / NORMAL / LOW
    "speed":       0.6,
    "hr":          0,
    "rmssd":       0.0,
    "cnn_state":   "NORMAL",
    "confidence":  0.0,
    "connected":   False
}

# ── WebSocket thread ─────────────────────────────────
def ws_thread():
    async def run():
        while True:
            try:
                async with websockets.connect(WS_URL) as ws:
                    ecg_state["connected"] = True
                    async for msg in ws:
                        d = json.loads(msg)
                        if d.get("type") in ("ecg_update", "init"):
                            ecg_state["heart_state"] = d.get("heart_state", "NORMAL")
                            ecg_state["speed"]       = d.get("speed",       0.6)
                            ecg_state["hr"]          = d.get("hr",          0)
                            ecg_state["rmssd"]       = d.get("rmssd",       0.0)
                            ecg_state["cnn_state"]   = d.get("cnn_state",   "NORMAL")
                            ecg_state["confidence"]  = d.get("confidence",  0.0)
            except:
                ecg_state["connected"] = False
            await asyncio.sleep(3)
    asyncio.run(run())

# ── La balle unique ──────────────────────────────────
class Ball:
    def __init__(self):
        self.x   = W // 2
        self.y   = H // 2
        self.r   = 22
        # Direction aléatoire
        angle    = random.uniform(0, math.pi * 2)
        self.vx  = math.cos(angle)
        self.vy  = math.sin(angle)
        self.trail = []  # traîne

    def update(self):
        # Vitesse basée sur ESP32 — PAS aléatoire
        spd = ecg_state["speed"] * 6  # pixels/frame

        self.x += self.vx * spd
        self.y += self.vy * spd

        # Rebond sur les murs
        if self.x - self.r < 0:
            self.x  = self.r
            self.vx = abs(self.vx)
        if self.x + self.r > W:
            self.x  = W - self.r
            self.vx = -abs(self.vx)
        if self.y - self.r < 60:
            self.y  = 60 + self.r
            self.vy = abs(self.vy)
        if self.y + self.r > H:
            self.y  = H - self.r
            self.vy = -abs(self.vy)

        # Traîne
        self.trail.append((int(self.x), int(self.y)))
        if len(self.trail) > 20:
            self.trail.pop(0)

    def contains(self, mx, my):
        return math.hypot(mx - self.x, my - self.y) <= self.r + 8

    def draw(self, surf):
        hs    = ecg_state["heart_state"]
        color = GREEN if hs == "HIGH" else RED if hs == "LOW" else CYAN

        # Traîne
        for i, (tx, ty) in enumerate(self.trail):
            alpha = int(80 * i / len(self.trail))
            tr_r  = max(2, int(self.r * i / len(self.trail) * 0.6))
            s     = pygame.Surface((tr_r*2+2, tr_r*2+2), pygame.SRCALPHA)
            pygame.draw.circle(s, (*color, alpha), (tr_r+1, tr_r+1), tr_r)
            surf.blit(s, (tx - tr_r - 1, ty - tr_r - 1))

        # Glow
        for radius, alpha in [(self.r+15, 30), (self.r+8, 60)]:
            gs = pygame.Surface((radius*2, radius*2), pygame.SRCALPHA)
            pygame.draw.circle(gs, (*color, alpha), (radius, radius), radius)
            surf.blit(gs, (int(self.x)-radius, int(self.y)-radius))

        # Balle principale
        pygame.draw.circle(surf, color,         (int(self.x), int(self.y)), self.r)
        pygame.draw.circle(surf, WHITE,         (int(self.x), int(self.y)), self.r, 2)
        pygame.draw.circle(surf, (*color, 100), (int(self.x), int(self.y)), int(self.r*0.5))

# ── ECG strip ────────────────────────────────────────
ecg_pts = [18.0] * 120
ecg_t   = 0.0

def update_ecg():
    global ecg_t
    ecg_t += 0.05
    v = 18 + math.sin(ecg_t * 8) * 6
    if math.sin(ecg_t * 8) > 0.9:
        v -= 12
    ecg_pts.append(max(2.0, min(34.0, v)))
    if len(ecg_pts) > 120:
        ecg_pts.pop(0)

def draw_ecg(surf, ox, oy):
    if len(ecg_pts) < 2:
        return
    pts = [(ox + i, oy + int(ecg_pts[i])) for i in range(len(ecg_pts))]
    pygame.draw.lines(surf, GREEN, False, pts, 2)

# ── Demo mode (sans ESP32) ────────────────────────────
demo_stress = 50.0
demo_target = 50.0

def demo_tick():
    global demo_stress, demo_target
    if ecg_state["connected"]:
        return
    if random.random() < 0.005:
        demo_target = random.uniform(20, 80)
    demo_stress += (demo_target - demo_stress) * 0.02

    # Simuler des vraies valeurs HR/RMSSD
    hr    = round(55 + demo_stress * 0.5)
    rmssd = round(60 - demo_stress * 0.4, 1)

    if hr < 65 and rmssd > 40:
        hs    = "HIGH"
        speed = 1.0
    elif hr > 90 or rmssd < 15:
        hs    = "LOW"
        speed = 0.2
    else:
        hs    = "NORMAL"
        speed = 0.6

    ecg_state["heart_state"] = hs
    ecg_state["speed"]       = speed
    ecg_state["hr"]          = hr
    ecg_state["rmssd"]       = rmssd

# ── MAIN ─────────────────────────────────────────────
def main():
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("HeartAim")
    pygame.mouse.set_visible(False)
    clock  = pygame.time.Clock()

    font_big   = pygame.font.SysFont("Courier New", 22, bold=True)
    font_med   = pygame.font.SysFont("Courier New", 16, bold=True)
    font_small = pygame.font.SysFont("Courier New", 11)

    ball  = Ball()
    score = 0
    combo = 0

    # Lancer WebSocket
    threading.Thread(target=ws_thread, daemon=True).start()

    running = True
    while running:
        clock.tick(FPS)
        mx, my = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

            # Clic sur la balle
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if ball.contains(mx, my):
                    combo += 1
                    pts    = round(100 * (1 + combo * 0.1) * ecg_state["speed"])
                    score += pts
                    # Nouvelle direction après clic
                    angle  = random.uniform(0, math.pi * 2)
                    ball.vx = math.cos(angle)
                    ball.vy = math.sin(angle)
                else:
                    combo = 0

        # Update
        demo_tick()
        update_ecg()
        ball.update()

        # ── Draw ─────────────────────────────────────
        screen.fill(BG)

        # Grid
        for x in range(0, W, 60):
            pygame.draw.line(screen, GRID, (x, 60), (x, H))
        for y in range(60, H, 60):
            pygame.draw.line(screen, GRID, (0, y), (W, y))

        # Balle
        ball.draw(screen)

        # Viseur
        hs      = ecg_state["heart_state"]
        ch_col  = GREEN if hs == "HIGH" else RED if hs == "LOW" else CYAN
        pygame.draw.circle(screen, ch_col, (mx, my), 16, 1)
        pygame.draw.circle(screen, ch_col, (mx, my), 4,  1)
        for dx, dy in [(-22,0),(22,0),(0,-22),(0,22)]:
            ex = mx + dx * 17 // 22
            ey = my + dy * 17 // 22
            pygame.draw.line(screen, ch_col, (mx+dx, my+dy), (ex, ey), 1)

        # ── UI Bar ───────────────────────────────────
        pygame.draw.rect(screen, (15,15,20), (0, 0, W, 55))
        pygame.draw.line(screen, (40,40,50), (0, 55), (W, 55), 1)

        # Dot connexion
        dot = GREEN if ecg_state["connected"] else ORANGE
        pygame.draw.circle(screen, dot, (18, 27), 5)
        lbl = "LIVE ESP32" if ecg_state["connected"] else "DEMO"
        screen.blit(font_small.render(lbl, True, (80,80,80)), (28, 20))

        # Score
        screen.blit(font_small.render("SCORE", True, (80,80,80)), (110, 10))
        screen.blit(font_big.render(str(score), True, WHITE), (110, 24))

        # HR
        screen.blit(font_small.render("HR (bpm)", True, (80,80,80)), (230, 10))
        hr_txt = str(ecg_state["hr"]) if ecg_state["hr"] > 0 else "--"
        screen.blit(font_big.render(hr_txt, True, RED), (230, 24))

        # RMSSD (HRV)
        screen.blit(font_small.render("HRV (rmssd)", True, (80,80,80)), (340, 10))
        screen.blit(font_big.render(str(ecg_state["rmssd"]), True, PURPLE), (340, 24))

        # Stress bar
        screen.blit(font_small.render("HEART RATE LEVEL", True, (80,80,80)), (480, 10))
        pygame.draw.rect(screen, (30,30,40), (480, 28, 180, 8), border_radius=4)
        bar_col = GREEN if hs == "HIGH" else RED if hs == "LOW" else BLUE
        bar_w   = {"HIGH": 180, "NORMAL": 110, "LOW": 40}[hs]
        pygame.draw.rect(screen, bar_col, (480, 28, bar_w, 8), border_radius=4)

        # Badge état
        badge_col = GREEN if hs == "HIGH" else RED if hs == "LOW" else BLUE
        badge_txt = font_med.render(hs, True, badge_col)
        bx = 690
        pygame.draw.rect(screen, (20,20,25), (bx, 12, badge_txt.get_width()+20, 30), border_radius=4)
        pygame.draw.rect(screen, badge_col, (bx, 12, badge_txt.get_width()+20, 30), 1, border_radius=4)
        screen.blit(badge_txt, (bx+10, 18))

        # CNN info
        cnn_str = f"CNN:{ecg_state['cnn_state']} {int(ecg_state['confidence']*100)}%"
        screen.blit(font_small.render(cnn_str, True, (80,80,80)), (800, 20))

        # Speed
        screen.blit(font_small.render("SPEED", True, (80,80,80)), (960, 10))
        screen.blit(font_big.render(f"{ecg_state['speed']:.2f}x", True, PURPLE), (960, 24))

        # ECG strip
        draw_ecg(screen, W-145, 16)

        # Combo
        if combo >= 3:
            ct = font_med.render(f"COMBO x{combo}", True, ORANGE)
            screen.blit(ct, (W - ct.get_width() - 20, H - 40))

        # Demo notice
        if not ecg_state["connected"]:
            n = font_small.render("MODE DEMO — Lance heartaim_server.py + connecte ESP32", True, ORANGE)
            nx = W//2 - n.get_width()//2
            pygame.draw.rect(screen, (25,15,5), (nx-10, H-32, n.get_width()+20, 22), border_radius=4)
            screen.blit(n, (nx, H-28))

        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    main()