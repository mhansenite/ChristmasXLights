"""Stage native LOR region effects; never overwrite active sequences or render files.

Run from the show root: python3 tools/rebuild_lor_native.py
Inputs are explicit in lor-native-manifest.json. Outputs and originals go to Backup.
"""
from pathlib import Path
import copy
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'Backup/2026-11-21-native-lor-rebuild'
MANIFEST = json.loads((ROOT / 'tools/lor-native-manifest.json').read_text())
TEMPLATES = json.loads((ROOT / 'tools/native-effect-templates.json').read_text())


def settings(text):
    return dict(v.split('=', 1) for v in text.split(',') if '=' in v)


def serialize(values):
    return ','.join(f'{k}={v}' for k, v in sorted(values.items()))


def number(value, default=1):
    try:
        return float(value)
    except ValueError:
        # LOR value curves are approximated by their first control value.
        match = re.match(r'[A-Z](-?[\d.]+)', value)
        return float(match[1]) if match else default


def native(component, duration):
    """Translate a source component to an editable xLights effect."""
    kind, colors, arguments = component.split(':', 2)
    kind = kind.removeprefix('lightorama_')
    args = arguments.split(',')
    active = [('#' + c.split(',')[0][-6:]) for c in colors.split(';') if c.endswith(',1')]
    if kind == 'none':
        return None
    names = {'colorwash': 'Color Wash', 'spinner': 'Pinwheel', 'spinfade': 'Pinwheel',
             'scanner': 'Bars', 'movingshapes': 'Shape', 'simpleshape': 'Shape',
             'straightlines': 'Bars', 'blendedbars': 'Bars', 'audio': 'VU Meter',
             'garland': 'Garlands', 'pinwheel': 'Pinwheel', 'ripple': 'Ripple',
             'curtain': 'Curtain', 'spirals': 'Spirals', 'butterfly': 'Butterfly',
             'twinkle': 'Twinkle', 'snowflakes': 'Snowflakes', 'fireworks': 'Fireworks',
             'meteors': 'Meteors', 'wave': 'Wave', 'bars': 'Bars'}
    if kind == 'text':
        # The only regional text cue in this batch is HTML containing a blank line.
        from urllib.parse import unquote
        import html
        plain = html.unescape(re.sub('<[^>]+>', '', unquote(args[0]))).strip()
        assert not plain, ('Untranslated regional text', plain)
        return None
    name = names[kind]
    opts = {k: v for k, v in settings(TEMPLATES[name]).items() if k.startswith('E_') and 'VALUECURVE' not in k}
    def arg(index, default=1):
        return number(args[index], default) if index < len(args) else default
    if kind == 'colorwash':
        if len(active) <= 1 or 'single_color' in arguments:
            name, opts = 'On', {}
        elif 'gradient' in arguments:
            name, kind = 'Bars', 'colorwash_gradient'
            opts = {'E_CHOICE_Bars_Direction': 'Left' if 'horizontal' in arguments else 'up',
                    'E_SLIDER_Bars_BarCount': '1', 'E_TEXTCTRL_Bars_Cycles': '0',
                    'E_CHECKBOX_Bars_Gradient': '1', 'E_CHECKBOX_Bars_3D': '0'}
            if 'diagonal' in arguments:
                opts.update({'E_CHOICE_Bars_Direction':'Custom','E_SLIDER_Bars_Angle':'45'})
        else:
            name, kind = 'Butterfly', 'colorwash_dither'
            opts = {'E_CHOICE_Butterfly_Colors':'Palette','E_CHOICE_Butterfly_Direction':'Normal',
                    'E_SLIDER_Butterfly_Chunks':'8','E_SLIDER_Butterfly_Skip':'2',
                    'E_SLIDER_Butterfly_Speed':'0','E_SLIDER_Butterfly_Style':'1'}
    elif name == 'Ripple':
        opts = {'E_CHOICE_Ripple_Draw_Style': 'Old', 'E_CHOICE_Ripple_Movement': 'Explode',
                'E_CHOICE_Ripple_Object_To_Draw': 'Circle', 'E_SLIDER_Ripple_XC': '0', 'E_SLIDER_Ripple_YC': '0',
                'E_SLIDER_Ripple_Thickness': str(max(3, min(100, int(arg(2, 15))))),
                'E_TEXTCTRL_Ripple_Cycles': str(max(.25, min(8, arg(1, 1))))}
    elif name == 'Pinwheel':
        opts.update({'E_SLIDER_PinwheelXC': '0', 'E_SLIDER_PinwheelYC': '0',
                     'E_SLIDER_Pinwheel_Arms': str(max(1, min(16, int(arg(2 if kind == 'spinner' else 0, 4))))),
                     'E_SLIDER_Pinwheel_ArmSize': '100', 'E_SLIDER_Pinwheel_Speed': '10',
                     'E_SLIDER_Pinwheel_Thickness': '35', 'E_SLIDER_Pinwheel_Twist': '0'})
    elif name == 'Bars':
        direction = args[0].lower()
        directions = {'default': 'up', 'v_expand': 'expand', 'v_compress': 'compress',
                      'down': 'down', 'up': 'up', 'top_to_bottom': 'down', 'bottom_to_top': 'up',
                      'left_to_right': 'Right', 'right_to_left': 'Left', 'left': 'Left', 'right': 'Right',
                      'left_and_right': 'H-expand', 'top_and_bottom': 'expand'}
        opts = {'E_CHOICE_Bars_Direction': directions.get(direction, 'up'),
                'E_SLIDER_Bars_BarCount': str(max(1, min(8, int(arg(1, 1)))) if kind == 'bars' else 1),
                'E_TEXTCTRL_Bars_Cycles': str(max(1, round(duration / 1500, 2))),
                'E_CHECKBOX_Bars_Gradient': '0'}
        if kind in ('scanner', 'straightlines'):
            active = (active or ['#FFFFFF']) + ['#000000'] * 4
    elif name == 'Curtain':
        opts = {'E_CHOICE_Curtain_Edge': args[0] if args[0] in ['top','bottom','left','right','center'] else 'center',
                'E_CHOICE_Curtain_Effect': args[1] if len(args)>1 and args[1] in ['open','close','open then close','close then open'] else 'open',
                'E_CHECKBOX_Curtain_Repeat': '0', 'E_SLIDER_Curtain_Swag': '0', 'E_TEXTCTRL_Curtain_Speed': '1.0'}
    elif name == 'Shape':
        shape = args[0].title()
        opts = {'E_CHOICE_Shape_ObjectToDraw': shape if shape in ['Circle','Star','Square','Triangle','Cross','Heart'] else 'Circle',
                'E_SLIDER_Shape_Count': str(max(1, min(12, int(arg(1, 3))))) if kind=='movingshapes' else '1',
                'E_SLIDER_Shape_StartSize': '30', 'E_SLIDER_Shape_Thickness': '12', 'E_SLIDER_Shape_Lifetime': '100',
                'E_SLIDER_Shapes_Velocity': '5' if kind=='movingshapes' else '0',
                'E_CHECKBOX_Shape_RandomLocation': '1' if kind=='movingshapes' else '0',
                'E_CHECKBOX_Shapes_RandomMovement': '1' if kind=='movingshapes' else '0'}
    elif name == 'Twinkle':
        opts = {'E_SLIDER_Twinkle_Count': '40', 'E_SLIDER_Twinkle_Steps': '12', 'E_CHECKBOX_Twinkle_Strobe': '0'}
    elif name == 'VU Meter':
        opts = {'E_CHOICE_VUMeter_Type':'Frame Waveform','E_SLIDER_VUMeter_Bars':'20','E_SLIDER_VUMeter_Gain':'30'}
    elif name == 'Fireworks':
        opts = {'E_CHECKBOX_FIRETIMING':'0','E_CHECKBOX_Fireworks_UseMusic':'0','E_SLIDER_Fireworks_Count':'20',
                'E_SLIDER_Fireworks_Fade':'30','E_SLIDER_Fireworks_Velocity':'3','E_SLIDER_Fireworks_XLocation':'50','E_SLIDER_Fireworks_YLocation':'50'}
    elif name == 'Spirals':
        opts.update({'E_SLIDER_Spirals_Count':str(max(1,min(8,int(arg(0,1))))),
                     'E_TEXTCTRL_Spirals_Movement':'1.0','E_SLIDER_Spirals_Thickness':'40'})
    elif name == 'Meteors':
        opts.update({'E_SLIDER_Meteors_Count':'15','E_SLIDER_Meteors_Speed':'15'})
    return name, opts, active or ['#FFFFFF'], kind


class Intern:
    def __init__(self, parent, tag):
        self.parent, self.tag = parent, tag
        self.ids = {e.text or '': str(i) for i, e in enumerate(parent)}
    def add(self, value):
        if value not in self.ids:
            self.ids[value] = str(len(self.parent))
            ET.SubElement(self.parent, self.tag).text = value
        return self.ids[value]


def merge(intervals):
    out=[]
    for start,end in sorted(intervals):
        if out and start<=out[-1][1]:out[-1][1]=max(end,out[-1][1])
        else:out.append([start,end])
    return out


def main():
    WORK.mkdir(exist_ok=True)
    layout_path=ROOT/'xlights_rgbeffects.xml'
    layout_text=layout_path.read_text(); layout=ET.fromstring(layout_text)
    additions=defaultdict(list); region_names={}; report=[]
    before_hashes={str(layout_path):hashlib.sha256(layout_path.read_bytes()).hexdigest()}
    models={m.get('name'):m for m in layout.findall('.//model')}
    def add_submodel(model,name,nodes,xy=False):
        key=(model,name)
        attrs={'name':name,'bufferstyle':'Keep XY' if xy else 'Default','layout':'horizontal',
               'line0':','.join(map(str,nodes)),'type':'ranges'}
        existing=models[model].find(f'subModel[@name="{name}"]')
        if key in region_names:assert region_names[key]==attrs;return name
        if existing is not None:assert existing.attrib==attrs
        else:additions[model].append(ET.Element('subModel',attrs))
        region_names[key]=attrs
        return name
    for entry in MANIFEST:
        path=ROOT/entry['file']; print('STAGE',path.name,flush=True)
        backup=WORK/'originals'/entry['file'];backup.parent.mkdir(parents=True,exist_ok=True)
        for p in [path,path.with_suffix('.fseq')]:
            before_hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
            dst=backup.with_suffix(p.suffix)
            if not dst.exists():shutil.copy2(p,dst)
        tree=ET.parse(path);root=tree.getroot()
        assert root.findall('.//Node'), ('Already migrated; use the saved originals for a new migration',path)
        palettes=Intern(root.find('ColorPalettes'),'ColorPalette');db=Intern(root.find('EffectDB'),'Effect')
        source=ET.parse(ROOT/entry['source']); wreath=source.find('.//SequenceProps/SeqProp[@name="H-Wreath"]')
        stats={'file':entry['file'],'source':entry['source'],'removed_node_effects':0,'native_region_effects':0,'regions':[], 'approximations':[]}
        for element in root.findall('./ElementEffects/Element'):
            name=element.get('name','');nodes=element.findall('Strand/Node')
            if not nodes:continue
            stats['removed_node_effects']+=sum(len(n) for n in nodes)
            if name!='PPD Wreath':
                # Each roof/window has two exact alternating-color cue tracks.
                signatures={}
                for n in nodes:
                    signature=tuple(tuple(sorted((k,v) for k,v in f.attrib.items() if k!='id')) for f in n)
                    signatures.setdefault(signature,n)
                assert len(signatures)==2,(path,name,len(signatures))
                templates=list(signatures.values())
                model=models[name]
                count=int(model.get('NodesPerString')) if name.startswith('Roof-') else int(model.get('TopNodes'))+int(model.get('BottomNodes'))+2*int(model.get('SideNodes'))
                if name.startswith('Roof-'):
                    templates.sort(key=lambda n: '#00FF00' not in root.find('ColorPalettes')[int(n[0].get('palette'))].text.upper())
                    labels=['LOR-Green','LOR-White']
                else:labels=['LOR-Odd','LOR-Even']
                for parity,(label,template) in enumerate(zip(labels,templates),1):
                    add_submodel(name,label,list(range(parity,count+1,2)))
                    layer=ET.SubElement(element,'SubModelEffectLayer',{'name':label})
                    for e in template:layer.append(copy.deepcopy(e))
            else:
                assert wreath is not None
                shape=source.find('.//PropClass[@Name="H-Wreath"]/shape')
                grid={(y,x):int(n) for y,row in enumerate(shape.get('CustomGrid').split(';')) for x,n in enumerate(row.split(',')) if n and int(n)>0}
                width,height=int(shape.get('CustomWidth')),int(shape.get('CustomHeight'))
                old_layers=element.findall('SubModelEffectLayer')
                existing_cues={(l.get('name'),int(e.get('startTime')),int(e.get('endTime'))) for l in old_layers for e in l}
                baked=merge((int(e.get('startTime')),int(e.get('endTime'))) for n in nodes for e in n)
                layers={}; timing=ET.SubElement(root.find('ElementEffects'),'Element',{'type':'timing','name':'LOR native wreath cues'})
                timing_layer=ET.SubElement(timing,'EffectLayer')
                ET.SubElement(root.find('DisplayElements'),'Element',{'type':'timing','name':'LOR native wreath cues','visible':'0','active':'0'})
                for track in wreath.findall('track'):
                    if not track.get('subc') or not len(track):continue
                    region=[]
                    for pair in track.get('subc').split(';'):
                        x,y=map(float,pair.split(','));pos=(round(y*height),round(x*width))
                        assert pos in grid,(path,track.get('name'),pos)
                        region.append(grid[pos])
                    region=sorted(set(region));assert len(region)>1
                    base='LOR-'+re.sub(r'[^\w -]','',track.get('name')).strip()
                    label=base
                    if (name,label) in region_names and region_names[(name,label)]['line0']!=','.join(map(str,region)):
                        label+='-'+hashlib.sha256(str(region).encode()).hexdigest()[:6]
                    for cue in track:
                        start,end=int(cue.get('startCentisecond'))*10,int(cue.get('endCentisecond'))*10
                        if (track.get('name'),start,end) in existing_cues:continue
                        if not any(start<b+25 and end>a-25 for a,b in baked):continue
                        components=[p for p in cue.get('settings','').split('|') if p.startswith('lightorama_')]
                        translated=[v for v in (native(p,end-start) for p in components) if v is not None]
                        if not translated:continue
                        add_submodel(name,label,region,xy=True)
                        if label not in stats['regions']:stats['regions'].append(label)
                        # Render each component in its own native layer; use black transparency
                        # for foreground motion so the source color fill stays visible.
                        for ci,(effect,opts,colors,source_kind) in enumerate(translated):
                            layer_index=len(translated)-1-ci
                            key=(label,layer_index)
                            if key not in layers:layers[key]=ET.Element('SubModelEffectLayer',{'name':label,'layer':str(layer_index)})
                            opts=opts.copy()
                            if len(translated)>1 and ci==1:opts['T_CHOICE_LayerMethod']='1 reveals 2'
                            brightness0=float(cue.get('startIntensity',cue.get('intensity','100')))
                            brightness1=float(cue.get('endIntensity',cue.get('intensity','100')))
                            if effect=='On':
                                opts.update({'E_TEXTCTRL_Eff_On_Start':str(brightness0),'E_TEXTCTRL_Eff_On_End':str(brightness1),
                                             'E_CHECKBOX_On_Shimmer':'1' if 'blink_in_unison' in cue.get('settings','') else '0'})
                            palette={f'C_BUTTON_Palette{i}':c for i,c in enumerate(colors[:8],1)}
                            palette.update({f'C_CHECKBOX_Palette{i}':'1' for i in range(1,min(8,len(colors))+1)})
                            if effect!='On':
                                if brightness0==brightness1:palette['C_SLIDER_Brightness']=str(brightness0)
                                else:palette['C_VALUECURVE_Brightness']=f'Active=TRUE|Id=ID_VALUECURVE_Brightness|Type=Ramp|Min=0.00|Max=400.00|P1={brightness0:.2f}|P2={brightness1:.2f}|RV=TRUE|'
                            ET.SubElement(layers[key],'Effect',{'name':effect,'startTime':str(start),'endTime':str(end),
                                            'ref':db.add(serialize(opts)),'palette':palettes.add(serialize(palette))})
                            stats['native_region_effects']+=1
                            if source_kind!='colorwash' or len(translated)>1:
                                stats['approximations'].append({'region':label,'start_ms':start,'end_ms':end,'source':source_kind,'native':effect})
                        ET.SubElement(timing_layer,'Effect',{'label':track.get('name')+': '+ ' + '.join(v[0] for v in translated),'startTime':str(start),'endTime':str(end)})
                # For composite cues, foreground is layer 0, background layer 1.
                for label in dict.fromkeys(key[0] for key in layers):
                    for ci in sorted(key[1] for key in layers if key[0]==label):
                        element.append(layers[(label,ci)])
                assert stats['native_region_effects']>0,(path,'no replacement wreath cues')
            for strand in list(element.findall('Strand')):element.remove(strand)
        assert not root.findall('.//Node'),path
        dest=WORK/'sequences'/entry['file'];dest.parent.mkdir(parents=True,exist_ok=True)
        tree.write(dest,encoding='UTF-8',xml_declaration=True)
        report.append(stats)
    for model,subs in additions.items():
        insertion='\n      '+'\n      '.join(ET.tostring(s,encoding='unicode') for s in subs)+'\n    '
        layout_text,n=re.subn(r'(<model name="'+re.escape(model)+r'".*?)(</model>)',lambda m:m[1]+insertion+m[2],layout_text,flags=re.S);assert n==1
    layout_text=re.sub(r'(?m)^[ \t]+$','',layout_text)
    ET.fromstring(layout_text)
    show=WORK/'show';show.mkdir(exist_ok=True)
    (show/'xlights_rgbeffects.xml').write_text(layout_text)
    shutil.copy2(ROOT/'xlights_networks.xml',show/'xlights_networks.xml')
    for directory in ROOT.iterdir():
        if directory.is_dir() and directory.name not in ['Backup','.git','.sequence-review','tools'] and not (show/directory.name).exists():
            (show/directory.name).symlink_to(directory,target_is_directory=True)
    (WORK/'migration-report.json').write_text(json.dumps(report,indent=2))
    (WORK/'input-hashes.json').write_text(json.dumps(before_hashes,indent=2))
    print('STAGED',len(report),'sequences;',sum(len(v) for v in additions.values()),'submodels;',sum(r['removed_node_effects'] for r in report),'node effects removed',flush=True)

if __name__=='__main__':
    main()
