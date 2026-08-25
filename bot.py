import time, requests, io, pytz, json, os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime
import numpy as np

# ===== CONFIGURATION NTFY =====
NTFY_XAU = os.getenv("NTFY_XAU", "https://ntfy.sh/rick-xau-sr-secret-2026")
NTFY_EUR = os.getenv("NTFY_EUR", "https://ntfy.sh/rick-eur-sr-secret-2026")
NTFY_GBP = os.getenv("NTFY_GBP", "https://ntfy.sh/rick-gbp-sr-secret-2026")
NTFY_V75 = os.getenv("NTFY_V75", "https://ntfy.sh/rick-v75-sr-secret-2026")

# ===== CONFIGURATION FACEBOOK =====
FB_PAGE_TOKEN = os.getenv("FB_PAGE_TOKEN")
FB_PAGE_ID = os.getenv("FB_PAGE_ID")

# ===== CONFIGURATION STORY =====
STORY_FILE = "story_count.txt"

PAIRS = {
    "XAUUSD": {"symbol": "GC=F", "ntfy": NTFY_XAU, "dec": 2, "name": "XAUUSD (Or)"},
    "EURUSD": {"symbol": "EURUSD=X", "ntfy": NTFY_EUR, "dec": 5, "name": "EURUSD"},
    "GBPUSD": {"symbol": "GBPUSD=X", "ntfy": NTFY_GBP, "dec": 5, "name": "GBPUSD"},
    "V75": {"symbol": "R_75", "ntfy": NTFY_V75, "dec": 2, "name": "Volatility 75", "source": "deriv"},
}

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def send(url, title, msg, img=None):
    for i in range(5):
        try:
            h = {"Title": title}
            if img:
                h["Filename"] = "chart.png"
                h["X-Message"] = msg
                r = requests.post(url, data=img, headers={k: v.encode() for k, v in h.items()}, timeout=30)
            else:
                r = requests.post(url, data=msg.encode(), headers=h, timeout=15)
            if r.status_code == 200:
                log(f"✅ {title}")
                return True
            log(f"⚠️ Tentative {i+1}: status {r.status_code}")
            time.sleep(2**i)
        except Exception as e:
            log(f"❌ Erreur: {e}")
            time.sleep(2**i)
    return False

# ===== FONCTIONS STORY =====
def get_story_count():
    """Récupère le nombre de stories publiées aujourd'hui"""
    try:
        with open(STORY_FILE, 'r') as f:
            date, count = f.read().strip().split(',')
            if date == datetime.now().strftime('%Y-%m-%d'):
                return int(count)
    except:
        pass
    return 0

def increment_story_count():
    """Incrémente le nombre de stories publiées aujourd'hui"""
    date = datetime.now().strftime('%Y-%m-%d')
    count = get_story_count() + 1
    with open(STORY_FILE, 'w') as f:
        f.write(f"{date},{count}")
    return count

def peut_publier_story():
    """Vérifie si on peut publier une story aujourd'hui"""
    jour = datetime.now().day
    if jour % 2 != 0:  # Jours impairs = pas de publication
        return False
    if get_story_count() >= 6:
        return False
    return True

def publier_story(page_id, page_token, message, image):
    """Publie une story sur Facebook avec image et texte"""
    try:
        if not page_token or not page_id:
            log("⏭️ Pas de token Facebook pour story")
            return False
        
        url_img = f"https://graph.facebook.com/v24.0/{page_id}/photos"
        files = {
            'source': ('chart.png', image, 'image/png'),
            'access_token': (None, page_token),
            'published': (None, 'false')
        }
        r_img = requests.post(url_img, files=files, timeout=30)
        if r_img.status_code != 200:
            log(f"⚠️ Story: erreur upload image {r_img.status_code}")
            return False
        
        img_id = r_img.json().get('id')
        if not img_id:
            log("⚠️ Story: pas d'ID d'image")
            return False
        
        url_story = f"https://graph.facebook.com/v24.0/{page_id}/stories"
        data_story = {
            "media_id": img_id,
            "access_token": page_token
        }
        r_story = requests.post(url_story, data=data_story, timeout=30)
        if r_story.status_code == 200:
            log(f"✅ Story publiée")
            increment_story_count()
            return True
        else:
            log(f"⚠️ Story: erreur {r_story.status_code}")
            return False
    except Exception as e:
        log(f"❌ Story erreur: {e}")
        return False

def publier_facebook(page_id, page_token, message, image=None):
    """Publie un message sur le feed Facebook"""
    try:
        if not page_token or not page_id:
            log("⏭️ Pas de token Facebook configuré")
            return False
        
        url = f"https://graph.facebook.com/v24.0/{page_id}/feed"
        data = {
            "message": message,
            "access_token": page_token
        }
        r = requests.post(url, data=data, timeout=30)
        if r.status_code == 200:
            log(f"✅ Facebook feed publié")
            return True
        else:
            log(f"⚠️ Facebook erreur feed: {r.status_code}")
            return False
    except Exception as e:
        log(f"❌ Facebook erreur: {e}")
        return False

def get_candles_deriv(sym):
    try:
        import websocket as ws_client
        log(f"🔌 Connexion Deriv pour {sym}...")
        ws = ws_client.create_connection('wss://ws.binaryws.com/websockets/v3?app_id=1089', timeout=10)
        ws.send(json.dumps({"ticks_history": sym, "count": 100, "end": "latest", "start": 1, "style": "candles", "granularity": 3600}))
        r = json.loads(ws.recv())
        ws.close()
        if "candles" in r:
            candles = [{"t": c["epoch"], "o": float(c["open"]), "h": float(c["high"]), "l": float(c["low"]), "c": float(c["close"])} for c in r["candles"]]
            log(f"✅ Deriv: {len(candles)} bougies pour {sym}")
            return candles
        else:
            log(f"⚠️ Deriv: pas de bougies pour {sym}")
            return []
    except Exception as e:
        log(f"❌ Deriv {sym}: {e}")
        return []

def get_candles(sym):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1h&range=60d"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        data = r.json()["chart"]["result"][0]
        closes = data["indicators"]["quote"][0]["close"]
        opens = data["indicators"]["quote"][0]["open"]
        highs = data["indicators"]["quote"][0]["high"]
        lows = data["indicators"]["quote"][0]["low"]
        timestamps = data["timestamp"]
        candles = []
        for i in range(len(closes)):
            if closes[i] and opens[i] and highs[i] and lows[i]:
                candles.append({"t": timestamps[i], "o": opens[i], "h": highs[i], "l": lows[i], "c": closes[i]})
        candles = candles[-100:] if len(candles) > 100 else candles
        log(f"✅ Yahoo: {len(candles)} bougies pour {sym}")
        return candles
    except Exception as e:
        log(f"❌ Yahoo {sym}: {e}")
        return []

def sr(cd, mx=3, tol=0.002):
    n = len(cd)
    rr, rs = [], []
    for i in range(5, n-5):
        if all(cd[j]["h"] <= cd[i]["h"] for j in range(max(0,i-5), min(n,i+6)) if j != i):
            rr.append(cd[i]["h"])
        if all(cd[j]["l"] >= cd[i]["l"] for j in range(max(0,i-5), min(n,i+6)) if j != i):
            rs.append(cd[i]["l"])
    def clust(lst):
        if not lst: return []
        lst = sorted(lst)
        zones, grp = [], [lst[0]]
        for v in lst[1:]:
            if (v-grp[0])/grp[0] <= tol:
                grp.append(v)
            else:
                zones.append((np.mean(grp), len(grp)))
                grp = [v]
        zones.append((np.mean(grp), len(grp)))
        return [z[0] for z in sorted(zones, key=lambda z: z[1], reverse=True)[:mx]]
    return sorted(clust(rr), reverse=True), sorted(clust(rs))

def channel(cd, lb=40):
    if len(cd) < 20:
        return None
    rc = cd[-lb:] if len(cd) >= lb else cd
    nr, off = len(rc), len(cd)-len(rc)
    ph, pl = [], []
    for i in range(2, nr-2):
        if all(rc[j]["h"] <= rc[i]["h"] for j in range(max(0,i-2), min(nr,i+3)) if j != i):
            ph.append((i, rc[i]["h"]))
        if all(rc[j]["l"] >= rc[i]["l"] for j in range(max(0,i-2), min(nr,i+3)) if j != i):
            pl.append((i, rc[i]["l"]))
    cls = [c["c"] for c in rc]
    sg = np.polyfit(np.arange(nr), cls, 1)[0]
    if sg >= 0:
        if len(pl) < 2: return None
        xs, ys = np.array([p[0] for p in pl]), np.array([p[1] for p in pl])
    else:
        if len(ph) < 2: return None
        xs, ys = np.array([p[0] for p in ph]), np.array([p[1] for p in ph])
    sl, ic = np.polyfit(xs, ys, 1)
    xa = np.arange(nr)
    base = sl*xa + ic
    hi = np.array([c["h"] for c in rc])
    lo = np.array([c["l"] for c in rc])
    return {"x": np.arange(off, len(cd)), "upper": base+np.max(hi-base), "lower": base+np.min(lo-base), "slope": sl}

def chart_sr(cd, cp, info):
    if len(cd) < 5:
        return None
    rz, sz = sr(cd)
    ch = channel(cd)
    name, dec = info["name"], info["dec"]
    fig, ax = plt.subplots(figsize=(18,10))
    fig.patch.set_facecolor('#0a0a0a')
    ax.set_facecolor('#0d1117')
    for i, c in enumerate(cd):
        col = '#26a69a' if c["c"]>=c["o"] else '#ef5350'
        ax.plot([i,i], [c["l"],c["h"]], color=col, lw=1.2)
        ax.add_patch(plt.Rectangle((i-0.35, min(c["o"],c["c"])), 0.7, abs(c["c"]-c["o"]) or 0.0001, facecolor=col, edgecolor=col))
    if ch:
        cc = '#a371f7' if ch["slope"]>0 else '#f0883e'
        ax.plot(ch["x"], ch["upper"], color=cc, lw=2.5, ls='--', alpha=0.9)
        ax.plot(ch["x"], ch["lower"], color=cc, lw=2.5, ls='--', alpha=0.9)
        ax.fill_between(ch["x"], ch["lower"], ch["upper"], color=cc, alpha=0.06)
    for r in rz:
        ax.axhline(r, color='#f85149', ls=':', lw=2.5)
        ax.text(len(cd)-1, r, f'  R {r:.{dec}f}', color='#f85149', fontsize=13, va='bottom', ha='right', fontweight='bold', bbox=dict(boxstyle='round,pad=0.3', facecolor='#1a0a0a', alpha=0.8))
    for s in sz:
        ax.axhline(s, color='#3fb950', ls=':', lw=2.5)
        ax.text(len(cd)-1, s, f'  S {s:.{dec}f}', color='#3fb950', fontsize=13, va='top', ha='right', fontweight='bold', bbox=dict(boxstyle='round,pad=0.3', facecolor='#0a1a0a', alpha=0.8))
    ax.axhline(cp, color='#f59e0b', ls='-.', lw=3)
    ax.text(2, cp, f' ► {cp:.{dec}f}', color='#f59e0b', fontsize=14, va='bottom', fontweight='bold', bbox=dict(boxstyle='round,pad=0.4', facecolor='#1a1400', alpha=0.85))
    n = len(cd)
    step = max(1, n//8)
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([datetime.fromtimestamp(cd[i]["t"]).strftime('%d/%m\n%Hh') for i in range(0,n,step)], color='white', fontsize=11)
    ax.set_title(f"  {name} — SR+Canal | Prix: {cp:.{dec}f}", color='white', fontsize=16, fontweight='bold', pad=15)
    ax.set_ylabel("Prix", color='white', fontsize=13)
    ax.tick_params(colors='white', labelsize=11)
    ax.grid(True, alpha=0.12, color='gray')
    for sp in ax.spines.values():
        sp.set_color('#333333')
    from matplotlib.patches import Patch
    leg = [Patch(color='#26a69a', label='Haussière'), Patch(color='#ef5350', label='Baissière'), Patch(color='#f85149', label='Résistance'), Patch(color='#3fb950', label='Support')]
    if ch:
        leg.append(Patch(color='#a371f7' if ch["slope"]>0 else '#f0883e', label=f'Canal {"↑" if ch["slope"]>0 else "↓"}'))
    ax.legend(handles=leg, loc='upper left', facecolor='#1a1a2e', edgecolor='#555', labelcolor='white', fontsize=12, framealpha=0.9)
    plt.tight_layout(pad=1.5)
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=130, facecolor='#0a0a0a')
    buf.seek(0)
    plt.close()
    return buf.getvalue()

def analyze(key, info):
    log(f"🔍 Analyse {key}...")
    src = info.get("source", "yahoo")
    if src == "deriv":
        cd = get_candles_deriv(info["symbol"])
    else:
        cd = get_candles(info["symbol"])
    if not cd:
        log(f"⚠️ Pas de données pour {key}")
        return
    
    cp = cd[-1]["c"]
    dec = info["dec"]
    rz, sz = sr(cd)
    ch = channel(cd)
    
    if ch:
        if ch["slope"] > 0.0001:
            tendance = "HAUSSIERE"
            tendance_icon = "📈"
        elif ch["slope"] < -0.0001:
            tendance = "BAISSIERE"
            tendance_icon = "📉"
        else:
            tendance = "LATERALE"
            tendance_icon = "📊"
    else:
        cls = [c["c"] for c in cd[-20:]]
        s = np.polyfit(np.arange(20), cls, 1)[0]
        tendance = "HAUSSIERE" if s>0.0001 else "BAISSIERE" if s<-0.0001 else "LATERALE"
        tendance_icon = "📈" if s>0.0001 else "📉" if s<-0.0001 else "📊"
    
    message = ""
    conseil = ""
    condition_remplie = False
    
    if rz and cp > rz[0] and tendance == "HAUSSIERE":
        condition_remplie = True
        conseil = "📈 ACHAT (Cassure Résistance + Canal HAUSSIER)"
        message = f"✅ Cassure de la résistance {rz[0]:.{dec}f} confirmée par la clôture à {cp:.{dec}f}"
    elif sz and cp < sz[0] and tendance == "BAISSIERE":
        condition_remplie = True
        conseil = "📉 VENTE (Cassure Support + Canal BAISSIER)"
        message = f"✅ Cassure du support {sz[0]:.{dec}f} confirmée par la clôture à {cp:.{dec}f}"
    
    if not condition_remplie:
        message = "❌ Condition non remplie pour ce trade"
        if rz and cp > rz[0] and tendance != "HAUSSIERE":
            message += f"\n⚠️ Cassure résistance {rz[0]:.{dec}f} mais canal {tendance} (pas aligné)"
        elif sz and cp < sz[0] and tendance != "BAISSIERE":
            message += f"\n⚠️ Cassure support {sz[0]:.{dec}f} mais canal {tendance} (pas aligné)"
        else:
            message += f"\n📊 Prix {cp:.{dec}f} dans le range S/R"
    
    full_msg = f"{message}\n\n💰 Prix: {cp:.{dec}f}\n📈 Tendance: {tendance_icon} {tendance}"
    if ch:
        full_msg += f"\n📏 Canal pente: {ch['slope']:.6f} ({'↑' if ch['slope']>0 else '↓'})"
    if rz:
        full_msg += f"\n🔴 Résistances: {', '.join([f'{r:.{dec}f}' for r in rz])}"
    if sz:
        full_msg += f"\n🟢 Supports: {', '.join([f'{s:.{dec}f}' for s in sz])}"
    h = datetime.now(pytz.timezone('Africa/Porto-Novo')).hour
    full_msg += f"\n🕒 {h}H Bénin\n🤖 SR Bot Trading"
    
    # ===== NTFY =====
    log(f"📤 Envoi notification {key}...")
    send(info["ntfy"], f"{key} - {conseil if condition_remplie else 'Analyse Horaire'}", full_msg)
    
    # ===== GRAPHIQUE =====
    img = chart_sr(cd, cp, info)
    if img:
        time.sleep(1)
        log(f"📤 Envoi graphique {key}...")
        send(info["ntfy"], f"{key} Graphique - {conseil if condition_remplie else 'Analyse'}", "SR+Canal", img)
    else:
        log(f"⚠️ Pas de graphique généré pour {key}")
    
    # ===== FACEBOOK FEED =====
    if FB_PAGE_TOKEN and FB_PAGE_ID:
        if img:
            log(f"📤 Publication Facebook {key}...")
            publier_facebook(FB_PAGE_ID, FB_PAGE_TOKEN, full_msg, img)
        else:
            log(f"📤 Publication Facebook {key} (sans image)...")
            publier_facebook(FB_PAGE_ID, FB_PAGE_TOKEN, full_msg, None)
    
    # ===== FACEBOOK STORY (si conditions remplies) =====
    if FB_PAGE_TOKEN and FB_PAGE_ID and condition_remplie and img:
        if peut_publier_story():
            log(f"📤 Publication story {key}...")
            publier_story(FB_PAGE_ID, FB_PAGE_TOKEN, full_msg, img)
        else:
            log(f"⏭️ Story: conditions non remplies pour {key}")
    else:
        log(f"⏭️ Pas de signal, pas de story pour {key}")

if __name__ == "__main__":
    log("🚀 SR BOT - Support & Résistance")
    now = datetime.now(pytz.timezone('Africa/Porto-Novo'))
    h, j = now.hour, now.weekday()
    
    log("→ V75 (7j/7)")
    analyze("V75", PAIRS["V75"])
    
    if j < 5:
        log(f"📊 Analyse Forex {h}H")
        for key in ["XAUUSD", "EURUSD", "GBPUSD"]:
            log(f"→ {key}")
            analyze(key, PAIRS[key])
    else:
        log(f"💤 Forex ferme week-end")
    
    log("✅ Termine")
