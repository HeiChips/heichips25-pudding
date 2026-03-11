#!/usr/bin/env python3
"""ngspice RAW analyzer – pure stdlib. Usage: python3 analyze_spice_raw.py file.raw [--csv] [--list-vars]"""
import argparse, math, os, re, struct, sys
from pathlib import Path

# ── parser ────────────────────────────────────────────────────────────────────
def parse_raw(path):
    raw, plots, pos = open(path,"rb").read(), [], 0
    while (bm := raw.find(b"Binary:\n", pos)) != -1:
        m, vs = {}, []
        for l in raw[pos:bm].decode(errors="replace").splitlines():
            l = l.strip()
            if   l.startswith("Plotname:"):     m["name"]  = l[9:].strip()
            elif l.startswith("No. Variables:"): m["nv"]   = int(l[14:])
            elif l.startswith("No. Points:"):   m["np"]    = int(l[11:])
            elif re.match(r"\d+\t", l):
                a = l.split("\t"); vs.append((int(a[0]), a[1].strip(), a[2].strip()))
        nv, np = m.get("nv",0), m.get("np",0)
        if nv and np:
            d = struct.unpack_from(f"<{nv*np}d", raw, bm+8)
            m["data"] = [d[i*nv:(i+1)*nv] for i in range(np)]
            m["vars"] = vs; plots.append(m); pos = bm + 8 + nv*np*8
        else: pos = bm + 1
    return plots

# ── helpers ───────────────────────────────────────────────────────────────────
def col(p, name):
    nl = name.lower()
    for i,(_, n, _) in enumerate(p["vars"]):
        if n.lower() == nl: return [r[i] for r in p["data"]]
    for i,(_, n, _) in enumerate(p["vars"]):
        if nl in n.lower(): return [r[i] for r in p["data"]]

def sweeps(p):
    s = [r[0] for r in p["data"]]
    rs = [i for i in range(1,len(s)) if s[i]-s[i-1] < -0.05]
    ni = rs[0] if rs else len(s)
    return ni, len(rs)+1, s[:ni]

def si(v, u=""):
    if not math.isfinite(v): return "n/a"
    for d,p in ((1e15,"f"),(1e12,"p"),(1e9,"n"),(1e6,"µ"),(1e3,"m"),(1,"")):
        if abs(v)*d >= 0.999 and abs(v)*d < 1000: return f"{v*d:.4g} {p}{u}".strip()
    return f"{v:.3e} {u}".strip()

def logi_vals(n): return [i*2/(max(n-1,1))-8 for i in range(n)]  # -8…-6

# ── text summary ──────────────────────────────────────────────────────────────
def summary(plots, path):
    out = [f"{'═'*68}", f"  {Path(path).name}", f"{'═'*68}"]
    for pi, p in enumerate(plots):
        nm = p.get("name","?")
        out.append(f"\n[{pi}] {nm}  ({p.get('np','?')} pts, {p.get('nv','?')} vars)")
        if "operating" in nm.lower():
            for _, n, t in p["vars"]:
                for k in ("ids","gm","gds","vth","vgs","vds","cgg","cgsol","cgdol"):
                    if k in n.lower():
                        out.append(f"  {n:<48} {si(p['data'][0][_], {"voltage":"V","current":"A","admittance":"S","capacitance":"F"}.get(t,"")):>14}"); break
        elif "dc" in nm.lower() or "transfer" in nm.lower():
            ni, no, vd = sweeps(p)
            ic, ir = col(p,"i(vd)"), col(p,"i(vprobe)")
            if ic is None: continue
            vi = min(range(len(vd)), key=lambda i: abs(vd[i]-0.6))
            out.append(f"  {no} IRef × {ni} VDS  ({vd[0]:.2f}…{vd[-1]:.2f} V)")
            out.append(f"  {'IRef':>10}  {'Iout@0.6V':>12}  {'Ratio':>8}  {'ro@0.6V':>12}")
            for k in range(no):
                iout = [-ic[k*ni+j] for j in range(ni)]
                iref_v = ir[k*ni+vi] if ir else 10**logi_vals(no)[k]
                ro = sorted(abs((vd[j]-vd[j-1])/(iout[j]-iout[j-1]+1e-30))
                            for j in range(1,ni) if 0.3<(vd[j]+vd[j-1])/2<0.9)[ni//4]
                out.append(f"  {si(iref_v,'A'):>10}  {si(iout[vi],'A'):>12}  "
                           f"{iout[vi]/(iref_v+1e-30):>8.5f}  {si(ro,'Ω'):>12}")
    out.append("\n"+"═"*68)
    return "\n".join(out)

# ── svg chart ─────────────────────────────────────────────────────────────────
PAL = ["#58a6ff","#3fb950","#ff7b72","#d2a8ff","#ffa657","#79c0ff","#56d364","#ff9492"]

def svg(W, H, title, series, xl, yl, xlog=False, ylog=False, hline=None):
    L,R,T,B = 72,20,36,48; w,h = W-L-R, H-T-B
    ax = [x for s in series for x in s[1] if math.isfinite(x) and (not xlog or x>0)]
    ay = [y for s in series for y in s[2] if math.isfinite(y) and (not ylog or y>0)]
    if not ax or not ay: return f'<svg width="{W}" height="{H}"></svg>'
    x0,x1 = min(ax),max(ax); y0,y1 = min(ay),max(ay)
    if x0==x1: x1=x0+1
    if y0==y1: y1=y0*10 if y0>0 else y0+1

    def px(x):
        if xlog: lx,l0,l1=math.log10(max(x,1e-300)),math.log10(max(x0,1e-300)),math.log10(max(x1,1e-300)); return L+(lx-l0)/(l1-l0+1e-30)*w
        return L+(x-x0)/(x1-x0)*w
    def py(y):
        if ylog: ly,l0,l1=math.log10(max(y,1e-300)),math.log10(max(y0,1e-300)),math.log10(max(y1,1e-300)); return T+h-(ly-l0)/(l1-l0+1e-30)*h
        return T+h-(y-y0)/(y1-y0)*h

    def ticks(a,b,log):
        if log:
            lo,hi=math.floor(math.log10(max(a,1e-300))),math.ceil(math.log10(max(b,1e-300)))
            return [10.**e for e in range(int(lo),int(hi)+1)]
        s=(b-a)/6; m=10**math.floor(math.log10(s)); s=min([1,2,2.5,5,10],key=lambda x:abs(x*m-s))*m
        v=math.ceil(a/s)*s; r=[]
        while v<=b+s*.01: r.append(round(v,12)); v+=s
        return r
    def ft(v):
        a=abs(v)
        for d,p in ((1e9,"G"),(1e6,"M"),(1e3,"k"),(1,""),(1e-3,"m"),(1e-6,"µ"),(1e-9,"n"),(1e-12,"p")):
            if a*1/d>=0.999 and a*1/d<1000: return f"{v/d:.3g}{p}"
        return f"{v:.2e}"

    o=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
       f'style="background:#161b22;border-radius:6px;display:block;margin:4px">']
    cid=f"c{abs(hash(title))%99999}"
    o.append(f'<defs><clipPath id="{cid}"><rect x="{L}" y="{T}" width="{w}" height="{h}"/></clipPath></defs>')
    for xv in ticks(x0,x1,xlog):
        p=px(xv)
        if L<=p<=L+w:
            o.append(f'<line x1="{p:.1f}" y1="{T}" x2="{p:.1f}" y2="{T+h}" stroke="#21262d"/>')
            o.append(f'<text x="{p:.1f}" y="{T+h+14}" fill="#8b949e" font-size="10" text-anchor="middle" font-family="monospace">{ft(xv)}</text>')
    for yv in ticks(y0,y1,ylog):
        p=py(yv)
        if T<=p<=T+h:
            o.append(f'<line x1="{L}" y1="{p:.1f}" x2="{L+w}" y2="{p:.1f}" stroke="#21262d"/>')
            o.append(f'<text x="{L-4}" y="{p+4:.1f}" fill="#8b949e" font-size="10" text-anchor="end" font-family="monospace">{ft(yv)}</text>')
    o.append(f'<rect x="{L}" y="{T}" width="{w}" height="{h}" fill="none" stroke="#30363d" stroke-width="1.5"/>')
    if hline is not None:
        p=py(hline); o.append(f'<line x1="{L}" y1="{p:.1f}" x2="{L+w}" y2="{p:.1f}" stroke="#555" stroke-dasharray="5,4"/>')
    for lbl,xs,ys,c in series:
        pts=" ".join(f"{px(x):.1f},{py(y):.1f}" for x,y in zip(xs,ys)
                     if math.isfinite(x) and math.isfinite(y) and (not xlog or x>0) and (not ylog or y>0))
        if pts: o.append(f'<polyline clip-path="url(#{cid})" points="{pts}" fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>')
    for i,(lbl,_,_,c) in enumerate(series[:8]):
        lx,ly=L+w-8,T+8+i*16
        o.append(f'<line x1="{lx-26}" y1="{ly+4}" x2="{lx-3}" y2="{ly+4}" stroke="{c}" stroke-width="2"/>')
        o.append(f'<text x="{lx-29}" y="{ly+8}" fill="#c9d1d9" font-size="9" text-anchor="end" font-family="monospace">{lbl}</text>')
    o.append(f'<text x="{L+w//2}" y="{H-5}" fill="#8b949e" font-size="11" text-anchor="middle" font-family="monospace">{xl}</text>')
    o.append(f'<text x="11" y="{T+h//2}" fill="#8b949e" font-size="11" text-anchor="middle" font-family="monospace" transform="rotate(-90,11,{T+h//2})">{yl}</text>')
    o.append(f'<text x="{L+w//2}" y="{T-10}" fill="#e6edf3" font-size="12" font-weight="bold" text-anchor="middle" font-family="monospace">{title}</text>')
    o.append("</svg>"); return "\n".join(o)

# ── html report ───────────────────────────────────────────────────────────────
CSS = """*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;color:#e6edf3;font-family:'Courier New',monospace;padding:28px;line-height:1.5}
h1{color:#58a6ff;font-size:1.3em;margin-bottom:4px} h2{color:#79c0ff;font-size:1em;margin:28px 0 10px;
padding-bottom:5px;border-bottom:1px solid #30363d} .s{color:#8b949e;font-size:.82em}
.ch{display:flex;flex-wrap:wrap;gap:6px} pre{background:#161b22;border:1px solid #30363d;
border-radius:6px;padding:14px;font-size:.79em;overflow-x:auto;color:#c9d1d9;margin:14px 0}
table{border-collapse:collapse;font-size:.83em} th,td{padding:5px 14px;border-bottom:1px solid #21262d}
th{background:#21262d;color:#58a6ff} tr:hover td{background:#161b22}"""

def html_report(plots, sumtxt, path):
    stem = Path(path).stem; secs = []
    for pi, p in enumerate(plots):
        nm = p.get("name","?")
        if "operating" in nm.lower():
            rows = "".join(f"<tr><td>{n}</td><td>{si(p['data'][0][i],{"voltage":"V","current":"A","admittance":"S","capacitance":"F"}.get(t,""))}</td></tr>"
                           for i,n,t in p["vars"]
                           if any(k in n.lower() for k in ("ids","gm","gds","vth","vgs","vds","cgg","cgsol","cgdol")))
            if rows: secs.append(f"<h2>Operating Point – Run {pi+1}</h2><table><tr><th>Variable</th><th>Wert</th></tr>{rows}</table>")
            continue
        if not ("dc" in nm.lower() or "transfer" in nm.lower()): continue
        ni, no, vd = sweeps(p)
        ic, ir = col(p,"i(vd)"), col(p,"i(vprobe)")
        if ic is None: continue
        lbls = [si(10**v,"A") for v in logi_vals(no)]

        s_ids   = [(lbls[k], vd, [-ic[k*ni+j] for j in range(ni)], PAL[k%8]) for k in range(no)]
        s_ratio = [(lbls[k], [vd[j] for j in range(ni) if vd[j]>.05],
                    [-(-ic[k*ni+j])/(ir[k*ni+j]+1e-30) for j in range(ni) if vd[j]>.05],
                    PAL[k%8]) for k in range(no)] if ir else []
        s_ro    = [(lbls[k],
                    [(vd[j]+vd[j-1])/2 for j in range(1,ni) if (vd[j]+vd[j-1])/2>.05],
                    [abs((vd[j]-vd[j-1])/(-ic[k*ni+j]+ic[k*ni+j-1]+1e-30)) for j in range(1,ni) if (vd[j]+vd[j-1])/2>.05],
                    PAL[k%8]) for k in range(no)]

        secs.append(f"<h2>DC Sweep – Run {pi+1} <span class=s>({no} I_ref × {ni} V_DS)</span></h2>"
                    f"<div class=ch>"
                    f"{svg(640,310,f'I_out vs V_DS',s_ids,'V_DS [V]','I_out [A]')}"
                    f"{svg(640,270,'Mirror Ratio −I_out/I_ref',s_ratio,'V_DS [V]','−I_out/I_ref',hline=1.0) if s_ratio else ''}"
                    f"{svg(640,270,'r_o vs V_DS',s_ro,'V_DS [V]','r_o [Ω]',ylog=True)}"
                    f"</div>")

    dc = [p for p in plots if "dc" in p.get("name","").lower() or "transfer" in p.get("name","").lower()]
    if len(dc)>=2:
        s_i, s_r = [], []
        for pi,p in enumerate(dc):
            ni,no,vd = sweeps(p); ic,ir = col(p,"i(vd)"),col(p,"i(vprobe)")
            if not ic: continue
            vi = min(range(len(vd)),key=lambda i:abs(vd[i]-.6))
            xs = [10**v for v in logi_vals(no)]
            ys_i = [-ic[k*ni+vi] for k in range(no)]
            s_i.append((f"Run {pi+1}", xs, ys_i, PAL[pi%8]))
            if ir: s_r.append((f"Run {pi+1}", xs, [-(-ic[k*ni+vi])/(ir[k*ni+vi]+1e-30) for k in range(no)], PAL[pi%8]))
        s_i.append(("ideal", xs, xs, "#555"))
        secs.append(f"<h2>Parametric Comparison</h2><div class=ch>"
                    f"{svg(640,300,'I_out @ V_DS=0.6V vs I_ref',s_i,'I_ref [A]','I_out [A]',xlog=True,ylog=True)}"
                    f"{svg(640,280,'Mirror Ratio vs I_ref',s_r,'I_ref [A]','−I_out/I_ref',xlog=True,hline=1.0) if s_r else ''}"
                    f"</div>")

    return (f"<!DOCTYPE html><html lang=de><head><meta charset=UTF-8>"
            f"<title>{stem}</title><style>{CSS}</style></head><body>"
            f"<h1>ngspice RAW – {stem}</h1><pre>{sumtxt}</pre>{''.join(secs)}</body></html>")

# ── main ──────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("raw"); ap.add_argument("--outdir",default="."); ap.add_argument("--csv",action="store_true"); ap.add_argument("--list-vars",action="store_true")
a = ap.parse_args()
os.makedirs(a.outdir, exist_ok=True)
pre = os.path.join(a.outdir, Path(a.raw).stem)

plots = parse_raw(a.raw)
print(f"{len(plots)} plot(s) in {a.raw}")

if a.list_vars:
    for pi,p in enumerate(plots):
        print(f"\n[{pi}] {p.get('name','?')}"); [print(f"  {i:3d}  {n:<50}  {t}") for i,n,t in p["vars"]]
    sys.exit()

s = summary(plots, a.raw); print(s)
open(f"{pre}_summary.txt","w").write(s); print(f"→ {pre}_summary.txt")

if a.csv:
    for pi,p in enumerate(plots):
        slug=re.sub(r"\W","_",p.get("name",f"p{pi}")).lower(); fn=f"{pre}_{slug}.csv"
        ni,no,_ = sweeps(p)
        with open(fn,"w") as f:
            f.write("sweep,"+",".join(n for _,n,_ in p["vars"])+"\n")
            [f.write(str(k//ni)+","+",".join(f"{v:.6e}" for v in r)+"\n") for k,r in enumerate(p["data"])]
        print(f"→ {fn}")

h = html_report(plots, s, a.raw); fn=f"{pre}.html"
open(fn,"w").write(h); print(f"→ {fn}")
