import os, re, time, requests
from datetime import date
from playwright.sync_api import sync_playwright

URL = "https://kbw-personal-services.butlerapp2.de/demo#/courses?fcourses=yaounde_deutsch_b2"
TOKEN = os.getenv("TG_TOKEN", "8716192422:AAFRetwBNgiGWG6eyUaNQdUs9Op694xkNO8")
CHAT_IDS = ["8806922221", "-5434725968"]

# Mémoire : { "02.11.2026 11:30": date_du_dernier_envoi }
notifie_libre_aujourdhui = {}
notifie_complet_aujourdhui = {}

def notify(text):
    for cid in CHAT_IDS:
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                          json={"chat_id": cid, "text": text, "parse_mode": "HTML"}, timeout=15)
        except: pass
    print(text)

def scan(page):
    libres = set()
    for pnum in range(1,5):
        page.wait_for_timeout(1200)
        cnt = page.locator('text=/\\d{1,2}:\\d{2} Uhr.*\\d{2}\\.\\d{2}\\.\\d{4}/').count()
        for i in range(cnt):
            try:
                h = page.locator('text=/\\d{1,2}:\\d{2} Uhr.*\\d{2}\\.\\d{2}\\.\\d{4}/').nth(i)
                txt = h.inner_text().strip()
                if not txt: continue
                h.click(); page.wait_for_timeout(600)
                has_b = page.locator('button, a').filter(has_text=re.compile(r'Buchen|Anmelden|Reservieren', re.I)).count() > 0
                full = page.locator('text=/ausgebucht|Warteliste/i').count() > 0
                dis = page.locator('button[disabled]').filter(has_text=re.compile(r'Buchen', re.I)).count()
                if has_b and not full and dis == 0:
                    libres.add(txt)
                try: h.click(); page.wait_for_timeout(150)
                except: pass
            except: continue
        if pnum < 4:
            try:
                nxt = page.locator(f'text="{pnum+1}"').first
                if nxt.count()>0: nxt.click()
                else: page.locator('text=">"').last.click()
                page.wait_for_timeout(2500)
            except: break
    return libres

notify("✅ Bot démarré - anti-doublon = même jour bloqué")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    page = browser.new_page()
    memo = set()
    first = True
    start = time.time()
    max_dur = 21000 if os.getenv("GITHUB_ACTIONS")=="true" else 999999999

    while time.time() - start < max_dur:
        # PHASE 1 : INITIALISATION
        print(f"\n🔵 PHASE 1 : INIT")
        try:
            page.goto(URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(4000)
        except:
            try: browser.close()
            except: pass
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page()
            continue

        # PHASE 2 : DETECTION
        print(f"🟡 PHASE 2 : DETECTION")
        actuelles = scan(page)
        print(f"  → {len(actuelles)} libres")

        if first:
            memo = actuelles
            first = False
            print(f"  Init: {len(memo)} mémorisées, pas de notif au 1er tour")
            continue

        # PHASE 3 : LIBRE - pas 2x même jour
        print(f"🟢 PHASE 3 : ENVOI LIBRE")
        for slot in actuelles:
            # Si déjà notifié aujourd'hui → on skip
            if slot in notifie_libre_aujourdhui and notifie_libre_aujourdhui[slot] == date.today():
                print(f"  ⏭️ Déjà notifié aujourd'hui: {slot}")
                continue
            # Sinon c'est nouveau OU un autre jour → on notifie
            if slot not in memo or notifie_libre_aujourdhui.get(slot) != date.today():
                notify(f"🔥 <b>LIBRE</b>\n📌 {slot}\n👉 {URL}")
                notifie_libre_aujourdhui[slot] = date.today()

        # PHASE 4 : REDEVENU COMPLET - pas 2x même jour
        print(f"🔴 PHASE 4 : COMPLET")
        redevenues = memo - actuelles
        for slot in redevenues:
            if slot in notifie_complet_aujourdhui and notifie_complet_aujourdhui[slot] == date.today():
                print(f"  ⏭️ Complet déjà notifié aujourd'hui: {slot}")
                continue
            notify(f"❌ <b>Redevenu complet</b>\n📌 {slot}")
            notifie_complet_aujourdhui[slot] = date.today()

        memo = actuelles
        print(f"🔄 Retour PHASE 1")
        page.wait_for_timeout(1000)
