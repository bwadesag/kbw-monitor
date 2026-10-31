
import os, re, time, requests
from playwright.sync_api import sync_playwright

URL = "https://kbw-personal-services.butlerapp2.de/demo#/courses?fcourses=yaounde_deutsch_b2"
TOKEN = os.getenv("TG_TOKEN", "8716192422:AAFRetwBNgiGWG6eyUaNQdUs9Op694xkNO8")
CHAT_IDS = os.getenv("TG_CHAT_IDS", "8806922221,-5434725968").split(",")

def notify(text):
    for cid in CHAT_IDS:
        cid = cid.strip()
        if not cid:
            continue
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={"chat_id": cid, "text": text, "parse_mode": "HTML"},
                timeout=15
            )
            print(f"Envoye a {cid}: {r.status_code}")
        except Exception as e:
            print(f"Erreur {cid}: {e}")

print("Demarrage scan")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    page = browser.new_page()
    page.goto(URL, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(8000)

    all_dispo = []

    for page_num in range(1, 5):
        print(f"--- PAGE {page_num}/4 ---")
        page.wait_for_timeout(3000)
        count = page.locator('text=/\d{1,2}:\d{2} Uhr.*\d{2}\.\d{2}\.\d{4}/').count()
        print(f"Events: {count}")

        for i in range(count):
            try:
                header = page.locator('text=/\d{1,2}:\d{2} Uhr.*\d{2}\.\d{2}\.\d{4}/').nth(i)
                txt = header.inner_text()
                print(f"Checking: {txt[:60]}")
                header.click()
                page.wait_for_timeout(1500)

                has_buchen = page.locator('button, a').filter(has_text=re.compile(r'Buchen|Anmelden|Reservieren|Reserver maintenant', re.I)).count() > 0
                is_full = page.locator('text=/ausgebucht|Warteliste|keine.*frei/i').count() > 0
                disabled_btn = page.locator('button[disabled]').filter(has_text=re.compile(r'Buchen', re.I)).count()

                if has_buchen and not is_full and disabled_btn == 0:
                    print(f"DISPO TROUVE: {txt}")
                    all_dispo.append(txt)
                else:
                    print("Complet")

                header.click()
                page.wait_for_timeout(600)
            except Exception as e:
                print(f"Err {i}: {e}")

        if page_num < 4:
            try:
                next_sel = page.locator(f'text="{page_num+1}"').first
                if next_sel.count() > 0:
                    next_sel.click()
                else:
                    page.locator('text=">"').last.click()
                page.wait_for_timeout(5000)
            except:
                break

    browser.close()
    print(f"RESULTAT: {len(all_dispo)} dispo sur 36")

    if all_dispo:
        detail = "\n".join([f"- {d[:120]}" for d in all_dispo[:10]])
        msg = f"🔥 <b>{len(all_dispo)} CRENEAU(X) B2 Yaounde DISPO !</b>\n\n{detail}\n\n👉 {URL}\n\nScanne 36 evenements (4 pages)"
        notify(msg)
    else:
        print("Aucun creneau dispo")
