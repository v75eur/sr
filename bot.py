import time, requests, io, pytz, json, os, urllib.parse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime
import numpy as np

NTFY_V75 = "https://ntfy.sh/rick-v75-sr-secret-2026"
NTFY_XAU = "https://ntfy.sh/rick-xau-sr-secret-2026"
TOPICS_RAPPORT = ["https://ntfy.sh/srbot-chaabane", "https://ntfy.sh/public"]
DERIV_ENDPOINTS = [
    'wss://api.derivws.com/trading/v1/options/ws/public',
    'wss://ws.derivws.com/websockets/v3?app_id=1089',
]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def send_image_avec_legende(url, title, legende, img):
    legende_courte = legende.replace("\n", " | ")
    url_full = url + "?message=" + urllib.parse.quote(legende_courte)
    r = requests.post(url_full, data=img, headers={"Title": title, "Filename": "chart.png"}, timeout=30)
    return r.status_code == 200

def get_candles_deriv(sym):
    import websocket as ws_client
    for endpoint in DERIV_ENDPOINTS:
        try:
            host = endpoint.split('/')[2]
            log(f"🔌 Deriv ({host}) pour {sym}...")
            ws = ws_client.create_connection(endpoint, timeout=20)
            ws.send(json.dumps({"ticks_history": sym, "count": 100, "end": "latest", "start": 1, "style": "candles", "granularity": 3600}))
            r = json.loads(ws.recv())
            ws.close()
            if "candles" in r:
                candles = [{"t": c["epoch"], "o": float(c["open"]), "h": float(c["high"]), "l": float(c["low"]), "c": float(c["close"])} for c in r["candles"]]
                log(f"✅ Deriv: {len(candles)} bougies")
                return candles
        except Exception as e:
            log(f"⚠️ {str(e)[:50]}")
            continue
    return []

def get_candles_yahoo(sym):
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
        log(f"❌ Yahoo: {e}")
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
    if len(cd) < 20: return None
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

def chart_sr(cd, cp, name, dec):
    if len(cd) < 5: return None
    rz, sz = sr(cd)
    ch = channel(cd)
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
        ax.text(len(cd)-1, r, f'  R {r:.{dec}f}', color='#f85149', fontsize=13, va='bottom', ha='right', fontweight='bold')
    for s in sz:
        ax.axhline(s, color='#3fb950', ls=':', lw=2.5)
        ax.text(len(cd)-1, s, f'  S {s:.{dec}f}', color='#3fb950', fontsize=13, va='top', ha='right', fontweight='bold')
    ax.axhline(cp, color='#f59e0b', ls='-.', lw=3)
    ax.text(2, cp, f' ► {cp:.{dec}f}', color='#f59e0b', fontsize=14, va='bottom', fontweight='bold')
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
        leg.append(Patch(color='#a371f7' if ch["slope"]>0 else '#f0883e', label='Canal'))
    ax.legend(handles=leg, loc='upper left', facecolor='#1a1a2e', edgecolor='#555', labelcolor='white', fontsize=12, framealpha=0.9)
    plt.tight_layout(pad=1.5)
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=130, facecolor='#0a0a0a')
    buf.seek(0)
    plt.close()
    return buf.getvalue()

def traiter_paire(nom, cd, dec, key):
    if not cd:
        log(f"⚠️ Pas de données {nom}")
        return
    cp = cd[-1]["c"]
    rz, sz = sr(cd)
    ch = channel(cd)

    if ch:
        if ch["slope"] > 0.0001: tendance = "HAUSSIERE"
        elif ch["slope"] < -0.0001: tendance = "BAISSIERE"
        else: tendance = "LATERALE"
    else:
        tendance = "LATERALE"

    res = f"{rz[0]:.{dec}f}" if rz else "—"
    sup = f"{sz[0]:.{dec}f}" if sz else "—"
    if ch and ch["slope"] > 0.0001: canal = "HAUSSIER"
    elif ch and ch["slope"] < -0.0001: canal = "BAISSIER"
    else: canal = "LATERAL"

    legende = (
        f"📊 RAPPORT {key}\n"
        f"Prix: {cp:.{dec}f}\n"
        f"Tendance: {tendance}\n"
        f"Canal: {canal}\n"
        f"R: {res}\n"
        f"S: {sup}\n"
        f"{datetime.now(pytz.timezone('Africa/Porto-Novo')).strftime('%H:%M')}H Benin\n"
        f"SR Bot\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📬 Une question ?\n"
        f"📱 WhatsApp : +229 60 31 54 58\n"
        f"💬 Groupe WhatsApp :\n"
        f"https://chat.whatsapp.com/EWD8yGDhm0aCr4AUEz4DmU"
    )

    # SIGNAL
    if rz and cp > rz[0] and tendance == "HAUSSIERE":
        legende += f"\n\n🔔 SIGNAL ACHAT\nCassure de la résistance {rz[0]:.{dec}f} confirmée à {cp:.{dec}f}"
        log(f"🔔 SIGNAL ACHAT {key}")
    elif sz and cp < sz[0] and tendance == "BAISSIERE":
        legende += f"\n\n🔔 SIGNAL VENTE\nCassure du support {sz[0]:.{dec}f} confirmée à {cp:.{dec}f}"
        log(f"🔔 SIGNAL VENTE {key}")

    img = chart_sr(cd, cp, nom, dec)

    for url in TOPICS_RAPPORT:
        log(f"📊 {key} → {url}")
        if img:
            ok = send_image_avec_legende(url, f"RAPPORT {key}", legende, img)
            log(f"{'✅' if ok else '❌'} {url}")
        time.sleep(2)

def main():
    log("🚀 SR BOT")
    now = datetime.now(pytz.timezone('Africa/Porto-Novo'))
    j = now.weekday()

    log("→ V75")
    cd_v75 = get_candles_deriv("R_75")
    traiter_paire("Volatility 75", cd_v75, 2, "V75")

    log("→ XAUUSD")
    if j < 5:
        cd_xau = get_candles_yahoo("GC=F")
        traiter_paire("XAUUSD (Or)", cd_xau, 2, "XAUUSD")
    else:
        legende = (
            f"📊 RAPPORT XAUUSD\n"
            f"💤 Marché fermé (week-end)\n"
            f"{datetime.now(pytz.timezone('Africa/Porto-Novo')).strftime('%H:%M')}H Benin\n"
            f"SR Bot\n"
            f"📱 WhatsApp: +229 60 31 54 58"
        )
        cd_xau = get_candles_yahoo("GC=F")
        img = chart_sr(cd_xau, cd_xau[-1]["c"], "XAUUSD (Or)", 2) if cd_xau else None
        for url in TOPICS_RAPPORT:
            log(f"📊 XAUUSD (fermé) → {url}")
            if img:
                send_image_avec_legende(url, "RAPPORT XAUUSD", legende, img)
            time.sleep(2)

    log("✅ Termine")

if __name__ == "__main__":
    main()
