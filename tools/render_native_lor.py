"""Render staged native replacements and unchanged-sequence baselines; do not promote."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,struct,subprocess
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'Backup/2026-11-21-native-lor-rebuild'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-only',action='store_true',help='Re-render refined native replacements, reusing validated baselines')
    parser.add_argument('--files-json',type=Path,help='Optional list of show-relative sequences to re-render')
    args=parser.parse_args()
    migrated={r['file'] for r in json.loads((WORK/'migration-report.json').read_text())}
    inputs=sorted((ROOT/'Sequences').rglob('*.xsq'))
    guards={str(p):digest(p) for p in [ROOT/'xlights_rgbeffects.xml',ROOT/'xlights_networks.xml',*inputs]}
    for p in inputs:
        if p.with_suffix('.fseq').exists():guards[str(p.with_suffix('.fseq'))]=digest(p.with_suffix('.fseq'))
    (WORK/'render-input-hashes.json').write_text(json.dumps(guards,indent=2))
    env=os.environ.copy();env.pop('XL_HEADLESS_RENDERCACHE',None)
    report=json.loads((WORK/'render-report.json').read_text()) if args.native_only else []
    if args.native_only:inputs=[p for p in inputs if str(p.relative_to(ROOT)) in migrated]
    if args.files_json:
        selected=set(json.loads(args.files_json.read_text()))
        inputs=[p for p in inputs if str(p.relative_to(ROOT)) in selected]
    for i,p in enumerate(inputs,1):
        rel=str(p.relative_to(ROOT)); staged=WORK/'sequences'/rel; changed=rel in migrated
        for mode,source in ([('rendered',staged)] if args.native_only else ([('baseline',p),('rendered',staged)] if changed else [('rendered',p)])):
            dest=WORK/mode/p.parent.relative_to(ROOT);dest.mkdir(parents=True,exist_ok=True)
            log=WORK/'logs'/mode/(p.stem+'.log');log.parent.mkdir(parents=True,exist_ok=True)
            print(f'RENDER {i}/{len(inputs)} {mode}: {p.name}',flush=True)
            with log.open('w') as f:
                result=subprocess.run(['/Applications/xLights.app/Contents/MacOS/xLights','--headless','--quiet','--show',str(WORK/'show'),'--outputdir',str(dest),str(source)],env=env,stdout=f,stderr=subprocess.STDOUT)
            out=dest/p.with_suffix('.fseq').name
            assert result.returncode==0 and out.exists(),(p,result.returncode,log)
            with out.open('rb') as f:header=f.read(32)
            assert header[:4]==b'PSEQ'
            channels,frames=struct.unpack_from('<II',header,10)
            old=p.with_suffix('.fseq')
            if old.exists():
                with old.open('rb') as f:previous=f.read(32)
                assert struct.unpack_from('<I',previous,14)[0]==frames and previous[18]==header[18],('Timing changed',p)
            report=[r for r in report if (r['file'],r['mode'])!=(rel,mode)]
            report.append({'file':rel,'mode':mode,'output':str(out.relative_to(ROOT)),'frames':frames,'channels':channels,'step_ms':header[18],'sha256':digest(out)})
            (WORK/'render-report.json').write_text(json.dumps(report,indent=2))
            print(f'OK {i}/{len(inputs)} {mode}',flush=True)
    for path,sha in guards.items():assert digest(Path(path))==sha,('Concurrent edit',path)
    print('All renders complete. Originals remain active pending validation.',flush=True)
if __name__=='__main__':main()
