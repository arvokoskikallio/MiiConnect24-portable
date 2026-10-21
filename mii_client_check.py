#!/usr/bin/env python3
"""Interactive Mii client-ID lookup against an existing MiiConnect24 index.
Python 3.10+, standard library only. Does not alter the index or assignments.

python mii_client_check.py
python mii_client_check.py --identities players.csv --nin-pids-json ninrankings_pids.json --mii-dir miis

1 Chadsoft profile (ID, URL or local JSON)
2 Local .rkg/.mii file or a direct ghost URL
3 NinRankings Top1000 profile URL/PID
4 Manual client ID (8-digit hex or decimal with 'dec:' prefix)

Profile lookups prefer local CTGP JSON, then the saved SQLite index. A profile
missing locally may be fetched online, reading each ghost's RKG header. Network
results are cached in mii_client_check_cache. Top1000 uses only your local PID-to-name JSON and Mii binaries, matched by
exact filename/stem. No Top1000 page requests or name-only client inference.
"""
import argparse
import binascii
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import unicodedata
from urllib.parse import urlparse,parse_qs
from urllib.request import Request,urlopen

BAD={'00000000','FFFFFFFF','80000000'}
CHAD='https://www.chadsoft.co.uk/time-trials/'


def useful(value):
    s=unicodedata.normalize('NFKC',str(value or '').replace('\x00',''))
    return int(' '.join(s.split()).casefold() not in {'','player','no name'})


def client_id(value):
    value=value.strip()
    if value.lower().startswith('dec:'):
        number=int(value[4:]);
        if not 0<=number<=0xffffffff:raise ValueError('Decimal client ID must be a 32-bit unsigned number')
        return f'{number:08X}'
    value=value.removeprefix('0x').removeprefix('0X')
    if re.fullmatch('[0-9a-fA-F]{8}',value):return value.upper()
    if value.isdecimal() and len(value)>8 and int(value)<=0xffffffff:return f'{int(value):08X}'
    raise ValueError('Enter 8 hex digits (e.g. 3A91E839), or dec:99717566')


def profile_url(pid):return CHAD+f'players/{pid[:2]}/{pid[2:]}.html'

def ghost_url(file):
    m=re.fullmatch(r'([0-9a-fA-F]{40})\.rkg',str(file),re.I)
    if not m:return ''
    h=m[1].upper();return CHAD+f'rkgd/{h[:2]}/{h[2:4]}/{h[4:]}.html'


def parse_mii(data,source):
    if data[:4]==b'RKGD':
        if len(data)<0x88:raise ValueError('Incomplete RKG header')
        m=data[0x3c:0x86]
        if binascii.crc_hqx(m,0)!=int.from_bytes(data[0x86:0x88],'big'):raise ValueError('Invalid Mii CRC16 in RKG')
    elif len(data) in (74,76):
        m=data[:74]
        if len(data)==76 and binascii.crc_hqx(m,0)!=int.from_bytes(data[74:76],'big'):raise ValueError('Invalid CRC16 in standalone Mii file')
    else:raise ValueError('Expected an RKGD ghost or a 74/76-byte Wii Mii file')
    return {'client':m[28:32].hex().upper(),'avatar':m[24:28].hex().upper(),
            'name':m[2:22].decode('utf-16-be',errors='replace').split('\x00',1)[0],
            'ghost':source,'url':source if source.startswith(('http://','https://')) else ''}


def download(url,cache,header=False):
    parsed=urlparse(url)
    if parsed.scheme not in ('http','https'):raise ValueError('Expected an http(s) URL')
    key=hashlib.sha256((url+('#header' if header else '')).encode()).hexdigest()
    path=cache/(key+'.bin')
    if path.is_file():return path.read_bytes()
    print('  Fetching '+url,flush=True)
    headers={'User-Agent':'MiiClientCheck/1.0'}
    if header:headers['Range']='bytes=0-135'
    with urlopen(Request(url,headers=headers),timeout=25) as r:
        data=r.read(0x88 if header else 20*1024*1024+1)
        if not header and len(data)>20*1024*1024:raise ValueError('Response exceeds 20 MiB')
    # Cache validated binary data only; failed HTML/error bodies remain retryable.
    if data[:4]==b'RKGD' or len(data) in (74,76):
        parse_mii(data,url);cache.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    return data


def json_miis(data,pid):
    if str(data.get('player_id','')).upper()!=pid:raise ValueError('JSON player_id differs from requested profile')
    if not isinstance(data.get('ghosts'),list):raise ValueError('Missing ghosts array')
    result=[]
    for i,g in enumerate(data['ghosts']):
        m=g.get('mii')
        if not isinstance(m,dict):raise ValueError(f'Ghost {i} has no Mii data')
        c=str(m.get('client_id') or '').upper();a=str(m.get('avatar_id') or '').upper()
        if not re.fullmatch('[0-9A-F]{8}',c):raise ValueError(f'Ghost {i} has invalid client_id')
        result.append({'client':c,'avatar':a,'name':str(m.get('name') or '').replace('\x00',''),'ghost':g.get('file',''),'url':ghost_url(g.get('file',''))})
    return result


def get_profile(value,args,db):
    path=Path(value.strip('"'))
    if path.is_file():
        with path.open(encoding='utf-8-sig') as f:data=json.load(f)
        pid=str(data.get('player_id') or '').upper()
        if not re.fullmatch('[0-9A-F]{16}',pid):raise ValueError('Invalid player_id in JSON')
        return json_miis(data,pid),{pid}
    pid=value.strip().upper()
    if not re.fullmatch('[0-9A-F]{16}',pid):
        m=re.search(r'/players/([0-9a-f]{2})/([0-9a-f]{14})\.(?:html|json)(?:[?#].*)?$',value,re.I)
        if not m:raise ValueError('Enter a Chadsoft profile URL, 16-character ID, or JSON path')
        pid=(m[1]+m[2]).upper()
    path=args.ctgp_dir/(pid+'.json')
    if not path.is_file() and args.ctgp_dir.is_dir():
        paths=[p for p in args.ctgp_dir.rglob('*.json') if p.stem.upper()==pid]
        if len(paths)>1:raise ValueError('Multiple JSON files found for this profile')
        if paths:path=paths[0]
    if path.is_file():
        print('  Reading local JSON: '+str(path))
        with path.open(encoding='utf-8-sig') as f:data=json.load(f)
        return json_miis(data,pid),{pid}
    if db:
        rows=db.execute('SELECT DISTINCT client,avatar,name,ghost FROM ctgp WHERE pid=?',(pid,)).fetchall()
        if rows:
            print('  Reading saved CTGP index.')
            return [dict(r)|{'url':ghost_url(r['ghost'])} for r in rows],{pid}
    # Raw Chadsoft profile JSON gives ghost URLs; Mii data lives in each RKG.
    data=json.loads(download(CHAD+f'players/{pid[:2]}/{pid[2:]}.json',args.cache).decode('utf-8-sig'))
    if str(data.get('playerId','')).upper()!=pid:raise ValueError('Live profile playerId does not match')
    ghosts=data.get('ghosts')
    if not isinstance(ghosts,list):raise ValueError('Live profile response lacks ghosts')
    if int(data.get('ghostCount',len(ghosts)))>len(ghosts):raise ValueError('Live response is incomplete; use a full local profile dump')
    result=[]
    for i,g in enumerate(ghosts,1):
        href=g.get('href')
        if not isinstance(href,str) or not re.fullmatch(r'/rkgd/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{36}\.rkg',href,re.I):raise ValueError('Unexpected live ghost URL')
        url=CHAD.rstrip('/')+href
        print(f'  Mii header {i}/{len(ghosts)}',flush=True)
        result.append(parse_mii(download(url,args.cache,True),url))
    return result,{pid}



def prepare_local_miis(args):
    if not args.nin_pids_json or not args.nin_pids_json.is_file():raise ValueError('Use --nin-pids-json with your local PID-to-Mii-names JSON')
    if not args.mii_dir.is_dir():raise ValueError('Mii folder missing: '+str(args.mii_dir)+'; set --mii-dir to your folder')
    if not hasattr(args,'_nin_pid_data'):
        args._nin_pid_data=json.loads(args.nin_pids_json.read_text(encoding='utf-8-sig'))
        if not isinstance(args._nin_pid_data,dict):raise ValueError('PID JSON must map profile IDs to lists of Mii names')
        for pid,names in args._nin_pid_data.items():
            if not pid.isdecimal() or not isinstance(names,list) or any(not isinstance(n,str) for n in names):raise ValueError('Expected numeric PID -> list of Mii-name strings')
    if not hasattr(args,'_mii_paths'):
        print('  Listing local Mii filenames (once for this session)...',flush=True)
        args._mii_paths=defaultdict(set)
        for path in args.mii_dir.rglob('*'):
            if path.is_file():
                args._mii_paths[path.name].add(path)
                args._mii_paths[path.stem].add(path)


def cached_mii(path,args):
    if not hasattr(args,'_mii_binary_cache'):
        args.cache.mkdir(parents=True,exist_ok=True)
        cache=sqlite3.connect(args.cache/'top1000_miis.sqlite3')
        cache.execute('CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY,mtime INTEGER,size INTEGER,result TEXT)')
        args._mii_binary_cache=cache
    cache=args._mii_binary_cache;stat=path.stat();key=str(path.resolve())
    old=cache.execute('SELECT mtime,size,result FROM files WHERE path=?',(key,)).fetchone()
    if old and old[0]==stat.st_mtime_ns and old[1]==stat.st_size:return json.loads(old[2])
    item=parse_mii(path.read_bytes(),str(path))
    with cache:cache.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?)',(key,stat.st_mtime_ns,stat.st_size,json.dumps(item,ensure_ascii=False)))
    return item


def top1000_matches(args):
    if hasattr(args,'_top_matches'):return args._top_matches
    if not args.nin_pids_json.is_file() or not args.mii_dir.is_dir():return {}
    prepare_local_miis(args)
    result=defaultdict(lambda:defaultdict(dict));missing=[];failures=[]
    entries=list(args._nin_pid_data.items())
    for i,(pid,names) in enumerate(entries,1):
        for n in names:
            n=n.replace('\x00','')
            if not useful(n):continue
            paths=args._mii_paths.get(n,set())
            if not paths:missing.append((pid,n));continue
            for path in sorted(paths):
                try:
                    item=cached_mii(path,args)
                    if useful(item['name']) and item['client'] not in BAD:result[item['client']][pid][str(path.resolve())]=item
                except (OSError,ValueError) as e:failures.append((str(path),str(e)))
        if i%500==0 or i==len(entries):print(f'  Local Top1000 Miis: {i}/{len(entries)} profiles checked',flush=True)
    args._top_matches={c:{pid:list(items.values()) for pid,items in profiles.items()} for c,profiles in result.items()}
    if missing or failures:
        args.cache.mkdir(parents=True,exist_ok=True)
        with (args.cache/'top1000_mii_issues.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f);w.writerow(['type','reference','details'])
            w.writerows(('missing',pid,n) for pid,n in missing)
            w.writerows(('unreadable',path,error) for path,error in failures)
        print(f'  Top1000 coverage incomplete: {len(missing)} missing names, {len(failures)} invalid files. See {args.cache/"top1000_mii_issues.csv"}')
    return args._top_matches


def top1000(value,args):
    """Read local Mii binaries referenced by a PID -> names JSON."""
    pid=value.strip()
    if not pid.isdecimal():
        u=urlparse(value)
        if u.hostname not in ('ninrankings.org','www.ninrankings.org') or u.path!='/mkwii/profil.php':raise ValueError('Expected a NinRankings Top1000 /mkwii/profil.php?id= URL')
        found=parse_qs(u.query).get('id',[])
        if len(found)!=1 or not found[0].isdigit():raise ValueError('Missing numeric profile ID')
        pid=found[0]
    prepare_local_miis(args)
    names=args._nin_pid_data.get(pid)
    if names is None:raise ValueError('NinRankings PID not present in the supplied JSON')
    result=[];missing=[];failures=[];seen=set()
    for n in names:
        n=n.replace('\x00','')
        if not useful(n):continue
        paths=args._mii_paths.get(n,set())
        if not paths:missing.append(n);continue
        if len(paths)>1:print(f'  {n!r}: {len(paths)} exact filename matches; checking all of them.')
        for path in sorted(paths):
            if path in seen:continue
            seen.add(path)
            try:
                item=cached_mii(path,args)
                # File mapping is taken literally; show the embedded name too.
                print('  Mii file:',path)
                print('    Embedded name:',repr(item['name']),'| client',item['client'],'| Mii ID',item['avatar'])
                result.append(item)
            except (OSError,ValueError) as exc:failures.append((str(path),str(exc)))
    for n in missing:print('  Missing local Mii file for JSON name:',repr(n))
    for path,error in failures:print('  Invalid/unreadable Mii file:',path,'|',error)
    if missing or failures:print('  INCOMPLETE: missing/invalid Mii files listed above were not included.')
    if not result:raise ValueError('No readable non-default Mii files found for this PID. JSON names must match exact filenames or filename stems, e.g. TheLetta Σ -> TheLetta Σ.mii.')
    print('  Read client IDs directly from local Mii binaries. No online lookup or PID-to-client conversion.')
    return result,set()


def connect(path):
    if not path.is_file():return None
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'ctgp','nin'}.issubset(tables):db.close();raise ValueError('Index is not a MiiConnect24 CTGP/NinRankings index')
    db.create_function('useful_mii',1,useful,deterministic=True)
    print('Loading default-Mii exclusions from the existing index...',flush=True)
    db.execute('CREATE TEMP TABLE blocked(client TEXT PRIMARY KEY)')
    db.execute("INSERT OR IGNORE INTO blocked SELECT client FROM ctgp WHERE useful_mii(name)=0 UNION SELECT client FROM nin WHERE useful_mii(name)=0")
    db.executescript('CREATE TEMP VIEW eligible_ctgp AS SELECT * FROM ctgp WHERE useful_mii(name)=1 AND client NOT IN(SELECT client FROM blocked); CREATE TEMP VIEW eligible_nin AS SELECT * FROM nin WHERE useful_mii(name)=1 AND client NOT IN(SELECT client FROM blocked);')
    return db


def owners(path):
    result={}
    if not path or not path.is_file():return result
    with path.open(encoding='utf-8-sig',newline='') as f:
        for i,row in enumerate(csv.DictReader(f),1):
            key=row.get('id') or str(i)
            label=row.get('name') or row.get('displayname') or ('MKWL #'+row['mkwl_id'] if row.get('mkwl_id') else 'Known player entry '+key)
            members={x.strip().upper() for x in row.get('ctgp_player_ids','').split(';') if x.strip()}
            for pid in members:result[pid]=(key,label,members)
    return result


def show_miis(rows,input_avatars):
    groups={}
    for row in rows:
        key=row['avatar'] or ('unknown',row['name'])
        item=groups.setdefault(key,{'names':set(),'rows':[]})
        item['names'].add(row['name']);item['rows'].append(row)
    for key,item in sorted(groups.items(),key=lambda kv:sorted(kv[1]['names'])):
        first=sorted(item['rows'],key=lambda r:str(r.get('ghost','')))[0]
        same=' [This Mii appears on both sides]' if first['avatar'] and first['avatar'] in input_avatars else ''
        print('    '+ ' / '.join(sorted(item['names']))+' | Mii ID '+(first['avatar'] or 'unavailable')+same)
        if first.get('url'):print('      Example: '+first['url'])
    return len(groups)


def check(miis,source_pids,db,known,top_matches=None,exclude_nin_pid=None):
    excluded=set(source_pids)
    for pid in source_pids:
        if pid in known:excluded.update(known[pid][2])
    grouped=defaultdict(list)
    for item in miis:
        if useful(item['name']) or item.get('manual'):grouped[item['client']].append(item)
    if not grouped:print('No usable non-default Miis found.');return
    has_mapping=db is not None and db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='nin_profiles'").fetchone()
    for client,items in sorted(grouped.items()):
        print('\n'+'='*64+'\nCLIENT '+client+' | decimal '+str(int(client,16)))
        if client in BAD or (db and db.execute('SELECT 1 FROM blocked WHERE client=?',(client,)).fetchone()):
            print('Excluded: placeholder/default-Mii client ID.');continue
        avatars={x['avatar'] for x in items if x['avatar'] and x['avatar'] not in BAD}
        if any(item['name'] for item in items):
            print('MIIS READ FROM YOUR INPUT:');show_miis(items,set())
        else:print('Client ID entered manually; no specific Mii/avatar supplied.')
        top=(top_matches or {}).get(client,{})
        visible={pid:rows for pid,rows in top.items() if pid!=exclude_nin_pid}
        print('\nMATCHING NINRANKINGS TOP1000 PROFILES:',len(visible))
        for pid,rows in sorted(visible.items()):
            print('  https://ninrankings.org/mkwii/profil.php?id='+pid)
            show_miis(rows,avatars)
        if db is None:
            print('No MiiConnect24 index: CTGP/Ghost Database comparisons unavailable.');continue
        ctgp=defaultdict(list)
        for row in db.execute('SELECT DISTINCT pid,avatar,name,ghost FROM eligible_ctgp WHERE client=? ORDER BY pid,ghost',(client,)):
            if row['pid'] in excluded:continue
            item=dict(row);item['url']=ghost_url(row['ghost']);ctgp[row['pid']].append(item)
        print('\nMATCHING CTGP PROFILES:',len(ctgp))
        for pid,rows in ctgp.items():
            print('  '+known.get(pid,('','Unknown player',set()))[1]+' | '+pid+' | '+str(len(rows))+' indexed ghosts')
            print('  '+profile_url(pid));show_miis(rows,avatars)
        nin=defaultdict(list);seen=set()
        for row in db.execute('SELECT * FROM eligible_nin WHERE client=? ORDER BY path',(client,)):
            ghost=row['ghost_id'] or row['path']
            if ghost in seen:continue
            seen.add(ghost)
            mapped=db.execute('SELECT profile_id FROM nin_profiles WHERE ghost_id=?',(row['ghost_id'],)).fetchone() if has_mapping else None
            pid=mapped[0] if mapped and mapped[0] else ''
            key=('profile',pid) if pid else ('mii',row['avatar'])
            item=dict(row);item['ghost']=ghost;item['url']='https://ninrankings.org/ghostdatabase/ghostviewer.php?id='+row['ghost_id'] if row['ghost_id'] else ''
            nin[key].append(item)
        print('\nMATCHING NINRANKINGS GROUPS:',len(nin))
        for (kind,pid),rows in nin.items():
            print('  '+('Profile '+pid if kind=='profile' else 'Mii with website profile ID not yet mapped')+' | '+str(len(rows))+' indexed ghosts')
            if kind=='profile':print('  https://ninrankings.org/ghostdatabase/profil.php?id='+pid)
            show_miis(rows,avatars)
        print('These profiles use Miis with the same origin/client ID. Different names or avatar IDs can still share that origin.')


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--index',type=Path,default=Path('mii_identity_matches/index.sqlite3'))
    p.add_argument('--ctgp-dir',type=Path,default=Path('ctgp_profiles'))
    p.add_argument('--identities',type=Path)
    p.add_argument('--nin-pids-json',type=Path,default=Path('ninrankings_pids.json'),help='Local PID -> Mii-name-list JSON')
    p.add_argument('--mii-dir',type=Path,default=Path('miis'),help='Local Wii Mii files, named as in the PID JSON (default miis)')
    p.add_argument('--cache',type=Path,default=Path('mii_client_check_cache'))
    args=p.parse_args();known=owners(args.identities);db=connect(args.index)
    if db is None:print('No index found at '+str(args.index)+'. IDs can still be read; use --index to enable local comparisons.')
    try:
        while True:
            print('\n1 Chadsoft profile\n2 Ghost/Mii file or direct ghost URL\n3 NinRankings Top1000 profile\n4 Enter client ID\nq Quit')
            choice=input('Choice: ').strip().lower()
            if choice=='q':break
            if choice not in {'1','2','3','4'}:continue
            try:
                value=input('Profile / file / client ID (blank cancels): ').strip().strip('"')
                if not value:continue
                source=set()
                if choice=='1':miis,source=get_profile(value,args,db)
                elif choice=='2':
                    if value.startswith(('http://','https://')):
                        url=value
                        parsed=urlparse(url)
                        if parsed.hostname in ('chadsoft.co.uk','www.chadsoft.co.uk') and parsed.path.endswith('.html') and '/rkgd/' in parsed.path:url=url.split('?',1)[0][:-5]+'.rkg'
                        miis=[parse_mii(download(url,args.cache),url)]
                    else:miis=[parse_mii(Path(value).read_bytes(),value)]
                elif choice=='3':miis,source=top1000(value,args)
                else:miis=[{'client':client_id(value),'avatar':'','name':'','ghost':'','url':'','manual':True}]
                top=top1000_matches(args)
                exclude_nin=None
                if choice=='3':exclude_nin=value if value.isdecimal() else parse_qs(urlparse(value).query).get('id',[None])[0]
                check(miis,source,db,known,top,exclude_nin)
            except Exception as exc:print('ERROR:',exc)
    finally:
        if db:db.close()
        if hasattr(args,'_mii_binary_cache'):args._mii_binary_cache.close()


if __name__=='__main__':
    try:main()
    except (EOFError,KeyboardInterrupt):print('\nClosed.')
    except (OSError,ValueError,sqlite3.Error) as exc:print('ERROR:',exc,file=sys.stderr);sys.exit(1)
