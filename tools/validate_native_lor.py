"""Validate staged native sequences and decoded renders without promoting them."""
from pathlib import Path
import json,xml.etree.ElementTree as ET
from collections import defaultdict
from fseq_frames import read_frames
ROOT=Path(__file__).resolve().parents[1];WORK=ROOT/'Backup/2026-11-21-native-lor-rebuild'

def ranges(ids):
    result=[]
    for n in sorted(set(ids)):
        if result and n==result[-1][1]:result[-1][1]+=1
        else:result.append([n,n+1])
    return result

def nodes(sub):
    values=set()
    for key,value in sub.attrib.items():
        if not key.startswith('line'):continue
        for token in value.split(','):
            ends=list(map(int,token.split('-')))
            values.update(range(min(ends),max(ends)+1))
    return values-{0}

def main():
    layout=ET.parse(WORK/'show/xlights_rgbeffects.xml')
    models={m.get('name'):m for m in layout.findall('.//model')}
    report=[]
    migration=json.loads((WORK/'migration-report.json').read_text())
    changed={r['file']:r for r in migration}
    for p in sorted((ROOT/'Sequences').rglob('*.xsq')):
        rel=str(p.relative_to(ROOT));fseq=WORK/'rendered'/p.relative_to(ROOT).with_suffix('.fseq')
        if not fseq.exists():continue
        seq=ET.parse(WORK/'sequences'/rel if rel in changed else p)
        assert not seq.findall('.//Node'),('Remaining node tracks',p)
        for e in seq.findall('./ElementEffects/Element'):
            if e.get('type')!='model' or e.get('name') not in models:continue
            model=models[e.get('name')];installed={s.get('name') for s in model.findall('subModel')}
            for sub in e.findall('SubModelEffectLayer'):assert sub.get('name') in installed,(p,sub.get('name'))
        roofs={};roof_random={}
        if rel in changed:
            oldseq=ET.parse(WORK/'originals'/rel)
            for element in oldseq.findall('./ElementEffects/Element'):
                name=element.get('name','')
                if not name.startswith('Roof-') or not element.findall('Strand/Node'):continue
                model=models[name]
                roofs[name]=(int(model.get('StartChannel').split(':')[-1])-1,int(model.get('NodesPerString')))
                roof_random[name]=[(int(e.get('startTime'))-25,int(e.get('endTime'))+25) for e in element.findall('Strand/Node/Effect') if e.get('name')=='Twinkle']
        baseline=read_frames(WORK/'baseline'/p.relative_to(ROOT).with_suffix('.fseq'),9561) if rel in changed else None
        excluded=set(range(1800)) if rel in changed and changed[rel]['native_region_effects'] else set()
        for start,count in roofs.values():excluded.update(range(start,start+3*count))
        unaffected=ranges(set(range(9561))-excluded)
        stochastic=[(int(e.get('startTime'))-25,int(e.get('endTime'))+25) for e in seq.findall('.//Effect') if e.get('name') in ['Twinkle','Fireworks','Snowflakes','Meteors','Shape','Butterfly']]
        # Check every new region cue has output somewhere within its duration.
        cues=[];wreath=seq.find('./ElementEffects/Element[@name="PPD Wreath"]')
        if rel in changed and wreath is not None:
            subs={s.get('name'):s for s in models['PPD Wreath'].findall('subModel')}
            for layer in wreath.findall('SubModelEffectLayer'):
                if not layer.get('name','').startswith('LOR-'):continue
                footprint=[(3*(n-1),3*n) for n in nodes(subs[layer.get('name')])]
                for effect in layer:
                    a,b=int(effect.get('startTime')),int(effect.get('endTime'))
                    cues.append({'region':layer.get('name'),'effect':effect.get('name'),'start_ms':a,'end_ms':b,'lit':False,'footprint':footprint})
        active=defaultdict(list)
        for cue in cues:
            for frame in range(cue['start_ms']//25,(cue['end_ms']+24)//25):active[frame].append(cue)
        roof_errors=[];outside_errors=[];random_diffs=0;roof_random_diffs=0;lit_frames=0;wreath_frames=0
        for fi,frame in enumerate(read_frames(fseq,9561)):
            lit_frames+=bool(frame.strip(b'\0'));wreath_frames+=bool(frame[:1800].strip(b'\0'))
            if baseline is not None:
                old=next(baseline)
                for name,(start,count) in roofs.items():
                    pair=old[start:start+6];expected=pair*(count//2)+(pair[:3] if count%2 else b'')
                    if frame[start:start+count*3]!=expected:
                        if any(a<=fi*25<=b for a,b in roof_random[name]):roof_random_diffs+=1
                        elif len(roof_errors)<12:roof_errors.append((name,fi*25))
                if any(frame[a:b]!=old[a:b] for a,b in unaffected):
                    if any(a<=fi*25<=b for a,b in stochastic):random_diffs+=1
                    elif len(outside_errors)<12:outside_errors.append(fi*25)
            for cue in active.get(fi,[]):
                if not cue['lit'] and any(frame[a:b].strip(b'\0') for a,b in cue['footprint']):cue['lit']=True
        if baseline is not None:
            try:next(baseline);raise AssertionError('Baseline longer')
            except StopIteration:pass
        dark=[{k:v for k,v in c.items() if k not in ['footprint','lit']} for c in cues if not c['lit'] and c['end_ms']-c['start_ms']>=25]
        item={'file':rel,'frames':fi+1,'lit_frames':lit_frames,'wreath_lit_frames':wreath_frames,'roof_errors':roof_errors,
              'unaffected_errors':outside_errors,'stochastic_difference_frames':random_diffs,'roof_twinkle_difference_frames':roof_random_diffs,'new_region_cues':len(cues),'dark_region_cues':dark}
        report.append(item);(WORK/'output-validation.json').write_text(json.dumps(report,indent=2))
        print(p.name,'roof errors',len(roof_errors),'unaffected errors',len(outside_errors),'dark region cues',len(dark),flush=True)
    print('Validated',len(report),'rendered sequences.',flush=True)
if __name__=='__main__':main()
