import time, requests, io, pytz, json, os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime
import numpy as np

NTFY_XAU = os.getenv("NTFY_XAU", "https://ntfy.sh/rick-xau-sr-secret-2026")
NTFY_EUR = os.getenv("NTFY_EUR", "https://ntfy.sh/rick-eur-sr-secret-2026")
NTFY_GBP = os.getenv("NTFY_GBP", "https://ntfy.sh/rick-gbp-sr-secret-2026")
NTFY_V75 = os.getenv("NTFY_V75", "https://ntfy.sh/rick-v75-sr-secret-2026")
NTFY_BT  = os.getenv("NTFY_BT",  "https://ntfy.sh/admin-sr")

PAIRS = {
    "XAUUSD": {"symbol": "GC=F", "ntfy": NTFY_XAU, "dec": 2, "name": "XAUUSD (Or)"},
    "EURUSD": {"symbol": "EURUSD=X", "ntfy": NTFY_EUR, "dec": 5, "name": "EURUSD"},
    "GBPUSD": {"symbol": "GBPUSD=X", "ntfy": NTFY_GBP, "dec": 5, "name": "GBPUSD"},
    "V75": {"symbol": "R_75", "ntfy": NTFY_V75, "dec": 2, "name": "Volatility 75", "source": "deriv"},
    "BT":  {"symbol": "R_75", "ntfy": NTFY_BT,  "dec": 2, "name": "Bot-Trade V75", "source": "deriv"},
}

DERIV_ENDPOINTS = [
    'wss://api.derivws.com/trading/v1/options/ws/public',
    'wss://ws.derivws.com/websockets/v3?app_id=1089',
    'wss://ws.binaryws.com/websockets/v3?app_id=1089',
]

TOPICS_RAPPORT = [
    "https://ntfy.sh/srbot-chaabane",
    "https://ntfy.sh/public",
]

FOOTER = (
    "━━━━━━━━━━━━━━━━━━━\n"
    "📬 Une question ?\n"
    "📱 WhatsApp : +229 60 31 54 58\n"
    "💬 Groupe WhatsApp :\n"
    "https://chat.whatsapp.com/EWD8yGDhm0aCr4AUEz4DmU"
)

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def get_active_users():
    try:
        if not os.path.exists("users.json"):
            return []
        with open("users.json", "r", encoding="utf-8") as f:
            users = json.load(f)
        today = datetime.now().strftime("%Y-%m-%d")
        actifs = []
        for pseudo, info in users.items():
            expire = info.get("expire", "")
            topic = info.get("topic", "")
            if not topic or not expire:
                continue
            if expire >= today:
                actifs.append((pseudo, topic))
        return actifs
    except Exception as e:
        log(f"⚠️ Erreur lecture users.json: {e}")
        return []

def send(url, title, msg, img=None):
    for i in range(5):
        try:
            h = {"Title": title}
            if img:
                h["Filename"] = "chart.png"
                h["X-Message"] = msg
                r = requests.post(url, data=img, headers={k: v.encode('utf-8') for k, v in h.items()}, timeout=30)
            else:
                r = requests.post(url, data=msg.encode('utf-8'), headers=h, timeout=15)
            if r.status_code == 200:
                log(f"✅ {title}")
                return True
            log(f"⚠️ Tentative {i+1}: status {r.status_code}")
            time.sleep(2**i)
        except Exception as e:
            log(f"❌ Erreur: {e}")
            time.sleep(2**i)
    return False

def get_candles_deriv(sym):
    import websocket as ws_client
    for endpoint in DERIV_ENDPOINTS:
        try:
            host = endpoint.split('/')[2]
            log(f"🔌 Connexion Deriv ({host}) pour {sym}...")
            ws = ws_client.create_connection(endpoint, timeout=20)
            ws.send(json.dumps({"ticks_history": sym, "count": 100, "end": "latest", "start": 1, "style": "candles", "granularity": 3600}))
            r = json.loads(ws.recv())
            ws.close()
            if "candles" in r:
                candles = [{"t": c["epoch"], "o": float(c["open"]), "h": float(c["high"]), "l": float(c["low"]), "c": float(c["close"])} for c in r["candles"]]
                log(f"✅ Deriv: {len(candles)} bougies pour {sym} ({host})")
                return candles
            else:
                log(f"⚠️ Deriv: pas de bougies ({host})")
        except Exception as e:
            log(f"⚠️ Échec {endpoint.split('/')[2]}: {str(e)[:60]}")
            continue
    log(f"❌ Deriv: tous les endpoints ont échoué pour {sym}")
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

def build_rapport(key, cp, dec, tendance, rz, sz, ch, marche_ferme=False):
    if marche_ferme:
        return (
            f"📊 RAPPORT HORAIRE - {key}\n\n"
            f"💤 Marché fermé (week-end)\n\n"
            f"{datetime.now(pytz.timezone('Africa/Porto-Novo')).strftime('%H:%M')}H Benin\n"
            f"SR Bot\n"
            f"{FOOTER}"
        )
    res_txt = f"{rz[0]:.{dec}f}" if rz else "—"
    sup_txt = f"{sz[0]:.{dec}f}" if sz else "—"
    if ch and ch["slope"] > 0.0001:
        canal_txt = "HAUSSIER ↑"
    elif ch and ch["slope"] < -0.0001:
        canal_txt = "BAISSIER ↓"
    else:
        canal_txt = "LATERAL →"
    return (
        f"📊 RAPPORT HORAIRE - {key}\n\n"
        f"Prix: {cp:.{dec}f}\n"
        f"Tendance: {tendance}\n"
        f"Canal: {canal_txt}\n"
        f"Résistance: {res_txt}\n"
        f"Support: {sup_txt}\n"
        f"{datetime.now(pytz.timezone('Africa/Porto-Novo')).strftime('%H:%M')}H Benin\n"
        f"SR Bot\n"
        f"{FOOTER}"
    )

def envoyer_rapport(key, cp, dec, tendance, rz, sz, ch, img, marche_ferme=False):
    msg = build_rapport(key, cp, dec, tendance, rz, sz, ch, marche_ferme)
    for url in TOPICS_RAPPORT:
        send(url, f"RAPPORT {key}", msg)
        if img:
            time.sleep(0.3)
            send(url, f"RAPPORT {key} - Graphique", "SR+Canal", img)

def analyze(key, info, is_weekend_forex=False):
    log(f"🔍 Analyse {key}...")

    # === CAS SPÉCIAL : Forex fermé le week-end ===
    if is_weekend_forex:
        log(f"💤 {key} - marché fermé (week-end)")
        envoyer_rapport(key, 0, info["dec"], "—", [], [], None, None, marche_ferme=True)
        return

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
        elif ch["slope"] < -0.0001:
            tendance = "BAISSIERE"
        else:
            tendance = "LATERALE"
    else:
        cls = [c["c"] for c in cd[-20:]]
        s = np.polyfit(np.arange(20), cls, 1)[0]
        tendance = "HAUSSIERE" if s>0.0001 else "BAISSIERE" if s<-0.0001 else "LATERALE"

    img = chart_sr(cd, cp, info)

    # === RAPPORT : seulement V75 et XAUUSD ===
    if key in ("V75", "XAUUSD"):
        log(f"📊 RAPPORT {key} → chaabane + public")
        envoyer_rapport(key, cp, dec, tendance, rz, sz, ch, img)

    # === SIGNAL ===
    conseil = ""
    msg = ""
    condition_remplie = False

    if rz and cp > rz[0] and tendance == "HAUSSIERE":
        condition_remplie = True
        conseil = "ACHAT (Cassure Resistance + Canal HAUSSIER)"
        msg = f"SIGNAL ACHAT SR\nCassure de la resistance {rz[0]:.{dec}f} confirmee par la cloture a {cp:.{dec}f}"
    elif sz and cp < sz[0] and tendance == "BAISSIERE":
        condition_remplie = True
        conseil = "VENTE (Cassure Support + Canal BAISSIER)"
        msg = f"SIGNAL VENTE SR\nCassure du support {sz[0]:.{dec}f} confirmee par la cloture a {cp:.{dec}f}"

    if condition_remplie:
        full_msg = (
            f"{msg}\n\n"
            f"Prix: {cp:.{dec}f}\n"
            f"Tendance: {tendance}\n"
            f"{datetime.now(pytz.timezone('Africa/Porto-Novo')).strftime('%H:%M')}H Benin\n"
            f"SR Bot\n"
            f"{FOOTER}"
        )
        log(f"📤 SIGNAL {key} - {conseil}")
        send(info["ntfy"], f"ALERTE {key} - {conseil}", full_msg)
        if img:
            time.sleep(0.5)
            send(info["ntfy"], f"{key} Graphique SIGNAL - {conseil}", "SR+Canal", img)
        for pseudo, topic in get_active_users():
            full_url = topic if topic.startswith("http") else f"https://ntfy.sh/{topic}"
            log(f"📤 SIGNAL user {pseudo} → {full_url}")
            send(full_url, f"ALERTE {key} - {conseil}", full_msg)
            if img:
                time.sleep(0.3)
                send(full_url, f"{key} Graphique SIGNAL - {conseil}", "SR+Canal", img)
    else:
        log(f"⏭️ SILENCE signal {key}")

if __name__ == "__main__":
    log("🚀 SR BOT - Support & Resistance")
    now = datetime.now(pytz.timezone('Africa/Porto-Novo'))
    h = now.hour
    j = now.weekday()  # 0=lundi, 5=samedi, 6=dimanche

    # 1. V75 (toujours) : rapport + signal
    log("→ V75 (7j/7)")
    analyze("V75", PAIRS["V75"])

    # 2. XAUUSD (rapport + signal) - si week-end : rapport "marche fermé"
    if j < 5:
        log(f"→ XAUUSD (Lundi-Vendredi)")
        analyze("XAUUSD", PAIRS["XAUUSD"])
    else:
        log(f"→ XAUUSD (week-end, marche ferme)")
        analyze("XAUUSD", PAIRS["XAUUSD"], is_weekend_forex=True)

    # 3. BT (signal uniquement, pas de rapport)
    log("→ BT (admin-sr) - signal uniquement")
    analyze("BT", PAIRS["BT"])

    # 4. Autres Forex (signal uniquement) - si semaine
    if j < 5:
        for key in ["EURUSD", "GBPUSD"]:
            log(f"→ {key}")
            analyze(key, PAIRS[key])

    log("✅ Termine")
