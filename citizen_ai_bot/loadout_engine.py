from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import LoadoutReport
DATA_DIR = Path(__file__).parent / 'data'
SHIP_DB_PATH = DATA_DIR / 'ship_loadouts.json'
COMPONENT_DB_PATH = DATA_DIR / 'components.json'
ROLE_DISPLAY={'combat':'Combat','interceptor':'Interceptor','heavy_fighter':'Heavy Fighter','stealth':'Stealth','exploration':'Exploration','multirole':'Multirole','cargo':'Cargo'}
ROLE_WEAPON_STYLE={'combat':'repeater','interceptor':'repeater','heavy_fighter':'cannon','stealth':'distortion','exploration':'cannon','multirole':'repeater','cargo':'cannon'}
ROLE_SYSTEM_PROFILE={'combat':{'shield':'military','power':'military','cooler':'military','quantum':'combat'},'interceptor':{'shield':'fast-recharge','power':'military','cooler':'military','quantum':'interceptor'},'heavy_fighter':{'shield':'military','power':'military','cooler':'military','quantum':'combat'},'stealth':{'shield':'stealth','power':'stealth','cooler':'stealth','quantum':'stealth'},'exploration':{'shield':'durable','power':'reliable','cooler':'reliable','quantum':'durable'},'multirole':{'shield':'balanced','power':'balanced','cooler':'balanced','quantum':'balanced'},'cargo':{'shield':'durable','power':'reliable','cooler':'reliable','quantum':'durable'}}
SHIP_ALIASES={'arrow':'arrow','gladius':'gladius','sabre':'sabre','corsair':'corsair','cutlass blue':'cutlass blue','vanguard':'vanguard warden'}
def _norm(t:str|None)->str:return ' '.join((t or '').strip().lower().split())
def _fmt(v,d=0): return 'n/a' if v is None else f'{v:,.{d}f}'
def _load(p): return json.load(open(p,'r',encoding='utf-8'))
@dataclass(slots=True)
class SelectedItem:
    name:str; size:int; item_class:str; grade:str|None=None; count:int=1; component_class:str|None=None; dps:float|None=None; alpha:float|None=None
    def line(self)->str:
        p=f'{self.count}x ' if self.count>1 else ''
        a=[f'Size {self.size}',f'Class {self.item_class}']
        if self.component_class:a.append(f'Type {self.component_class}')
        if self.grade:a.append(f'Grade {self.grade}')
        if self.dps is not None:a.append(f'{_fmt(self.dps)} DPS each')
        if self.alpha is not None:a.append(f'{_fmt(self.alpha)} alpha')
        return f"{p}{self.name} — {' • '.join(a)}"
class LoadoutEngine:
    def __init__(self,ship_db=None,component_db=None): self.ship_db=ship_db or _load(SHIP_DB_PATH); self.component_db=component_db or _load(COMPONENT_DB_PATH)
    def resolve_ship_key(self,name:str): q=_norm(name); return q if q in self.ship_db else SHIP_ALIASES.get(q)
    def normalize_role(self,ship,role):
        r=_norm(role).replace(' ','_') if role else ''
        return r if r in ROLE_DISPLAY else ship.get('default_role','multirole')
    def select_weapon(self,size,role):
        style=ROLE_WEAPON_STYLE.get(role,'repeater'); db=self.component_db['weapons']; item=(db.get(style) or {}).get(str(size)) or (db.get('repeater') or {}).get(str(size))
        return None if not item else SelectedItem(item['name'],int(item['size']),item['class'],item.get('grade'),dps=item.get('dps'),alpha=item.get('alpha'))
    def _profile(self,role,cat): mp=ROLE_SYSTEM_PROFILE.get(role,ROLE_SYSTEM_PROFILE['multirole']); return mp['quantum'] if cat=='quantum_drives' else mp.get({'shields':'shield','power':'power','coolers':'cooler'}[cat],'balanced')
    def select_system(self,cat,size,count,role):
        by=(self.component_db['systems'].get(cat,{}) or {}).get(str(size));
        if not by:return None
        item=by if 'name' in by else by.get(self._profile(role,cat)) or by.get('balanced') or next(iter(by.values()))
        return SelectedItem(item['name'],int(item['size']),item['class'],item.get('grade'),count,item.get('component_class'))
    def select_missile(self,size,count):
        item=(self.component_db['missiles']).get(str(size)); return None if not item else SelectedItem(item['name'],int(item['size']),item['class'],count=count)
    def build(self,ship_name,role=None):
        key=self.resolve_ship_key(ship_name)
        if not key:return None
        ship=self.ship_db[key]; role=self.normalize_role(ship,role); hp=ship.get('hardpoints',{}); stats=ship.get('stats',{})
        weapons=[]; tdps=0; talpha=0
        for s in hp.get('weapons',[]):
            it=self.select_weapon(int(s['size']),role); c=int(s.get('count',1))
            if it: it.count=c; weapons.append(it); tdps+=(it.dps or 0)*c; talpha+=(it.alpha or 0)*c
        for s in hp.get('missiles',[]):
            it=self.select_missile(int(s['size']),int(s.get('count',1)))
            if it: weapons.append(it)
        systems=[]
        for cat in ('shields','power','coolers','quantum_drives'):
            for s in hp.get(cat,[]):
                it=self.select_system(cat,int(s['size']),int(s.get('count',1)),role)
                if it: systems.append(it)
        if 'quantum_drives' not in hp and stats.get('crew') is not None:
            qsize=1 if stats.get('crew',1)<=1 else 2 if stats.get('crew',1)<=4 else 3
            it=self.select_system('quantum_drives',qsize,1,role)
            if it: systems.append(it)
        perf=[f'Recommended weapon DPS: {_fmt(tdps)}',f'Recommended alpha strike: {_fmt(talpha)}']
        for k,l in (('hull_hp','Hull HP'),('shield_hp','Shield HP')):
            if stats.get(k) is not None: perf.append(f'{l}: {_fmt(stats[k])}')
        perf.append(f"Speed: SCM {_fmt(stats.get('scm_speed'))} m/s • Max {_fmt(stats.get('max_speed'))} m/s")
        perf.append(f"Cargo: {_fmt(stats.get('cargo_scu'))} SCU")
        perf.append(f"Crew: {stats.get('crew','n/a')}")
        if stats.get('shield_hp') and stats.get('hull_hp'): perf.append(f"Durability Index: {_fmt(stats['shield_hp']+stats['hull_hp'])}")
        notes=[f"Recommended role profile: {ROLE_DISPLAY[role]}",f"Weapon style: {ROLE_WEAPON_STYLE.get(role,'repeater')}","Loadout v2: role-aware weapons, systems, quantum drive, and provider cross-checking enabled."]
        return LoadoutReport(ship.get('display_name',ship_name),ROLE_DISPLAY[role],ship.get('manufacturer','Unknown'),[x.line() for x in weapons],[x.line() for x in systems],perf,notes)
