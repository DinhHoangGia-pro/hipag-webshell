import re, glob, os, json, statistics, subprocess
RUN="experiments/runs/rq1_codebert"; MAXEP=25; PAT=5
secs=[]
for f in glob.glob(os.path.join(RUN,"seed_*/metrics.json")):
    try: secs+=[e["seconds"] for e in json.load(open(f)).get("history",[]) if "seconds" in e]
    except: pass
spe=statistics.median(secs) if secs else 670.0
try: lines=open(os.path.join(RUN,"run.log")).read().splitlines()
except FileNotFoundError: lines=[]
seed=epoch=batch=tot=None; best=bad=None
for ln in lines:
    m=re.search(r'seed=(\d+) epoch=(\d+) batch=(\d+)/(\d+)', ln)
    if m: seed,epoch,batch,tot=map(int,m.groups())
    v=re.search(r'seed=(\d+) epoch=(\d+) val_PR-AUC=([\d.]+) best=([\d.]+)@(\d+) bad=(\d+)/(\d+)', ln)
    if v: seed=int(v.group(1)); best=(float(v.group(4)),int(v.group(5))); bad=(int(v.group(6)),int(v.group(7)))
alive=any("run_codebert_baseline.py" in o and "grep" not in o for o in subprocess.getoutput("ps -eo cmd").splitlines())
done=sorted(d.split('/')[-2] for d in glob.glob(os.path.join(RUN,"seed_*/metrics.json")))
print(f"Seed HOÀN TẤT: {len(done)}/5  {done}")
print(f"Train: {'ĐANG CHẠY' if alive else 'KHÔNG (ở gate [y/N] hoặc đã dừng)'}")
if seed is not None: print(f"Seed log: {seed} | epoch {epoch}/{MAXEP} | batch {batch}/{tot}")
if best: print(f"Best val PR-AUC: {best[0]:.4f} @epoch{best[1]} | bad={bad[0]}/{bad[1]}")
print(f"~{spe/60:.1f} phút/epoch")
if alive and epoch:
    stop_lo=min((best[1]+PAT) if best else MAXEP, MAXEP)
    lo=max(stop_lo-epoch,0); hi=max(MAXEP-epoch,0)
    print(f"ETA seed này: {lo}-{hi} epoch ~ {spe*lo/60:.0f}-{spe*hi/60:.0f} phut")
elif not alive and len(done)<5:
    print(">> Dang cho may bam y o gate Copilot de chay seed ke.")
elif len(done)>=5:
    print(">> DU 5 SEED. Gui tao codebert_rq1_summary.json de lam bang RQ1.")
