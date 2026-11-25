import os, re, time, requests
from datetime import date, datetime, timedelta, timezone

COURSES = (
    ("Yaounde B2", "https://kbw-personal-services.butlerapp2.de/demo#/courses?fcourses=yaounde_deutsch_b2"),
    ("Douala B2", "https://kbw-personal-services.butlerapp2.de/demo#/courses?fcourses=douala_deutsch_b2"),
)
TOKEN = os.getenv("TG_TOKEN", "")
CHAT_IDS = ["8806922221", "-5434725968"]
# ponytail: 8 pages is the ceiling. The loop stops earlier when the next page number is absent.
MAX_PAGES = 8

notifie_libre_aujourdhui = {}
notifie_complet_aujourdhui = {}

def notify(text):
    for cid in CHAT_IDS:
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={"chat_id": cid, "text": text, "parse_mode": "HTML"},
                timeout=15,
            )
            if response.status_code != 200:
                print(f"  telegram {response.status_code} {response.text[:160]}")
        except Exception as exc:
            print(f"  telegram: {exc}")
    print(text)

def _is_libre(cls, text):
    # The site shows the date, then the time: "26.11.2026 8:00 Uhr".
    # A full row carries the class booked-out. A free row does not.
    text = " ".join((text or "").split())
    if re.search(r"booked-out|waiting|warteliste", cls or "", re.I):
        return False
    if re.search(r"ausgebucht|warteliste", text, re.I):
        return False
    return bool(re.search(r"\d{2}\.\d{2}\.\d{4}", text) and re.search(r"\d{1,2}:\d{2}", text))

def _self_check():
    assert _is_libre("ws-data-row", "26.11.2026 8:00 Uhr")
    assert _is_libre("ws-data-row", "8:00 Uhr 26.11.2026")
    assert not _is_libre(
        "ws-data-row ws-data-row-booked-out ws-course-yaounde_deutsch_b2",
        "26.11.2026 8:00 Uhr",
    )
    assert not _is_libre("ws-data-row", "Start Time")
    assert not _is_libre("ws-data-row ws-data-row-waiting", "02.12.2026 11:30 Uhr")
    assert not _is_libre(
        "ws-data-row ws-data-row-booked-out ws-course-douala_deutsch_b2",
        "26.11.2026 8:00 Uhr",
    )
    assert _lien("Douala B2 — 26.11.2026 8:00 Uhr").endswith("douala_deutsch_b2")
    assert _lien("Yaounde B2 — 26.11.2026 8:00 Uhr").endswith("yaounde_deutsch_b2")
    assert _dans_horaire(datetime(2026, 11, 25, 7, 0, tzinfo=timezone.utc))
    assert not _dans_horaire(datetime(2026, 11, 25, 6, 59, tzinfo=timezone.utc))
    assert _dans_horaire(datetime(2026, 11, 25, 16, 59, tzinfo=timezone.utc))
    assert not _dans_horaire(datetime(2026, 11, 25, 17, 0, tzinfo=timezone.utc))
    print("self-check ok")

def _dans_horaire(moment_utc):
    # 8:00 inclus, 18:00 exclus, heure du Cameroun (UTC+1, sans changement d'heure).
    return 8 <= (moment_utc + timedelta(hours=1)).hour < 18

def _lien(slot):
    for city, url in COURSES:
        if slot.startswith(city):
            return url
    return COURSES[0][1]

def collect(page):
    found = set()
    failed = 0
    for city, url in COURSES:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4000)
            slots = {f"{city} — {slot}" for slot in scan(page)}
        except Exception as exc:
            failed += 1
            print(f"  {city}: {exc}")
            continue
        print(f"  {city}: {len(slots)} libres")
        found |= slots
    if failed == len(COURSES):
        raise RuntimeError("aucune page")
    return found

def scan(page):
    libres = set()
    for pnum in range(1, MAX_PAGES + 1):
        page.wait_for_timeout(1200)
        rows = page.locator("tr.ws-data-row")
        for i in range(rows.count()):
            row = rows.nth(i)
            cls = row.get_attribute("class") or ""
            txt = " ".join(row.inner_text().split())
            if _is_libre(cls, txt):
                libres.add(txt)
        if pnum >= MAX_PAGES:
            break
        try:
            nxt = page.get_by_text(str(pnum + 1), exact=True)
            if nxt.count() > 0:
                nxt.first.click()
            else:
                page.get_by_text(">", exact=True).last.click()
            page.wait_for_timeout(1500)
        except Exception:
            break
    return libres

def main():
    from playwright.sync_api import sync_playwright

    if not _dans_horaire(datetime.now(timezone.utc)):
        print("hors plage 8h-18h, arret")
        return
    notify("✅ Bot démarré - Yaounde B2 et Douala B2 - 8h à 18h")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        memo = set()
        first = True
        # ponytail: 5h40 stays under the 6h Actions job limit. The 13:50 run covers the rest until 18:00.
        deadline = time.time() + (5 * 60 + 40) * 60

        while time.time() < deadline and _dans_horaire(datetime.now(timezone.utc)):
            print("\n🔵 PHASE 1 : INIT")
            print("🟡 PHASE 2 : DETECTION")
            try:
                actuelles = collect(page)
            except Exception as exc:
                print(f"  pages: {exc}")
                try:
                    browser.close()
                except Exception:
                    pass
                browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
                page = browser.new_page()
                continue
            detail = ", ".join(sorted(actuelles))
            print(f"  → {len(actuelles)} libres" + (f" : {detail}" if detail else ""))

            if first:
                memo = actuelles
                first = False
                print(f"  Init: {len(memo)} mémorisées, pas de notif au 1er tour")
                continue

            print("🟢 PHASE 3 : ENVOI LIBRE")
            for slot in actuelles:
                if slot in notifie_libre_aujourdhui and notifie_libre_aujourdhui[slot] == date.today():
                    print(f"  ⏭ Déjà notifié aujourd'hui: {slot}")
                    continue
                if slot not in memo or notifie_libre_aujourdhui.get(slot) != date.today():
                    notify(f"🔥 <b>LIBRE</b>\n📌 {slot}\n👉 {_lien(slot)}")
                    notifie_libre_aujourdhui[slot] = date.today()

            print("🔴 PHASE 4 : COMPLET")
            redevenues = memo - actuelles
            for slot in redevenues:
                if slot in notifie_complet_aujourdhui and notifie_complet_aujourdhui[slot] == date.today():
                    print(f"  ⏭ Complet déjà notifié aujourd'hui: {slot}")
                    continue
                notify(f"❌ <b>Redevenu complet</b>\n📌 {slot}")
                notifie_complet_aujourdhui[slot] = date.today()

            memo = actuelles
            print("🔄 Retour PHASE 1")
            page.wait_for_timeout(1000)
        print("passage termine")


if __name__ == "__main__":
    if os.getenv("SELF_CHECK") == "1":
        _self_check()
    else:
        main()
