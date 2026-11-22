"""Refresh alternating-pixel submodels after changing a roof/window pixel count.

Defaults to an audit. Pass --write to update the layout, then reload xLights
and re-render sequences. Existing region submodels keep their physical pixels.
"""
import argparse,re,xml.etree.ElementTree as ET
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layout',type=Path,default=Path('xlights_rgbeffects.xml'))
    parser.add_argument('--write',action='store_true')
    args=parser.parse_args();text=args.layout.read_text();root=ET.fromstring(text);changes=[]
    for model in root.findall('.//model'):
        targets=[s for s in model.findall('subModel') if s.get('name') in ['Odd','Even','LOR-Green','LOR-White','LOR-Odd','LOR-Even']]
        if not targets:continue
        count=int(model.get('NodesPerString')) if model.get('DisplayAs')=='Poly Line' else int(model.get('TopNodes'))+int(model.get('BottomNodes'))+2*int(model.get('SideNodes'))
        for sub in targets:
            parity=1 if sub.get('name') in ['Odd','LOR-Green','LOR-Odd'] else 2
            value=','.join(map(str,range(parity,count+1,2)))
            if value==sub.get('line0'):continue
            changes.append((model.get('name'),sub.get('name')))
            pattern=r'(<model name="'+re.escape(model.get('name'))+r'".*?<subModel name="'+re.escape(sub.get('name'))+r'"[^>]*line0=")[^"]*'
            text,n=re.subn(pattern,lambda m:m[1]+value,text,flags=re.S);assert n==1
    if args.write and changes:ET.fromstring(text);args.layout.write_text(text)
    print(('Updated' if args.write else 'Need updating')+f': {len(changes)} alternating submodels')
    for model,sub in changes:print(model+'/'+sub)
    if changes and not args.write:raise SystemExit(1)
if __name__=='__main__':main()
