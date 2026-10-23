#!/usr/bin/env python3
"""MiiConnect24 Portable: interactive Mii client-ID lookup from local dumps.
Python 3.10+, standard library only. Never changes source dumps or assignments.
Automatically builds a reusable local SQLite cache; no prebuilt index required.

python mii_client_check.py
python mii_client_check.py --ctgp-dir ctgp_profiles --ninrankings-dir ninrankings
python mii_client_check.py --identities players.csv --nin-pids-json ninrankings_pids.json --mii-dir miis
python mii_client_check.py --refresh-index --index-only

1 Chadsoft profile (ID, URL or local JSON)
2 Local .rkg/.mii file or a direct ghost URL
3 NinRankings Top1000 profile URL/PID
4 Manual client ID (8-digit hex or decimal with 'dec:' prefix)

Profile lookups prefer local CTGP JSON, then the saved SQLite index. A profile
missing locally may be fetched online, reading each ghost's RKG header. Network
results are cached in mii_client_check_cache. Top1000 uses only your local PID-to-name JSON and Mii binaries, matched by
exact filename/stem. No Top1000 page requests or name-only client inference.
Friend codes are computed only from Top1000 online PIDs. Ghost Database
profile links use the decimal Mii client ID, never the friend-code formula.
"""
import argparse
import binascii
from collections import defaultdict
import csv
from contextlib import contextmanager
import os
import time
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


def top1000_friend_code(pid):
    """Convert an online/Top1000 PID, never a Mii client ID, into an MKW FC."""
    value=str(pid)
    if not re.fullmatch('[0-9]+',value) or not 0<=int(value)<=0xffffffff:raise ValueError('Online PID must be a 32-bit unsigned integer')
    number=int(value);checksum=hashlib.md5(number.to_bytes(4,'little')+b'JCMR').digest()[0]>>1
    code=f'{((checksum<<32)|number) if number else 0:012d}'
    return '-'.join(code[i:i+4] for i in (0,4,8))


def ghost_database_profile_url(client):
    value=str(client or '').upper()
    if not re.fullmatch('[0-9A-F]{8}',value) or value in BAD:return ''
    return 'https://ninrankings.org/ghostdatabase/profil.php?id='+str(int(value,16))


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
            if not pid.isdecimal() or not 0<int(pid)<=0xffffffff or not isinstance(names,list) or any(not isinstance(n,str) for n in names):raise ValueError('Expected numeric PID -> list of Mii-name strings')
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
    print('  Input Top1000 profile PID:',pid,'| Friend code:',top1000_friend_code(pid))
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



@contextmanager
def dump_index_lock(cache):
    cache.mkdir(parents=True,exist_ok=True)
    with (cache/'dump_index.lock').open('a+b') as stream:
        try:
            if os.name=='nt':
                import msvcrt
                stream.seek(0);stream.write(b'0');stream.flush();stream.seek(0)
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:raise ValueError('Another Portable process is building the comparison cache. Close it and retry.') from exc
        try:yield
        finally:
            if os.name=='nt':
                stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def open_dump_index(path):
    # Only our marked cache may be opened for writes. Explicit --index stays read-only.
    if path.exists():
        check=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
        try:
            marked=check.execute("SELECT value FROM portable_meta WHERE key='schema'").fetchone()
            if not marked or marked[0]!='1':raise ValueError('Unrecognised cache schema; use a different --cache folder')
        except sqlite3.Error as exc:raise ValueError('Existing dump_index.sqlite3 is not a Portable cache; choose another --cache folder') from exc
        finally:check.close()
    db=sqlite3.connect(path,timeout=30);db.row_factory=sqlite3.Row
    db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS portable_meta(key TEXT PRIMARY KEY,value TEXT);
        INSERT OR IGNORE INTO portable_meta VALUES('schema','1');
        CREATE TABLE IF NOT EXISTS portable_files(kind TEXT,path TEXT,mtime INTEGER,size INTEGER,error TEXT,PRIMARY KEY(kind,path));
        CREATE TABLE IF NOT EXISTS ctgp(path TEXT,pid TEXT,ghost TEXT,avatar TEXT,client TEXT,name TEXT,creator TEXT,PRIMARY KEY(path,pid,ghost));
        CREATE TABLE IF NOT EXISTS nin(path TEXT PRIMARY KEY,ghost_id TEXT,avatar TEXT,client TEXT,name TEXT,creator TEXT);
        CREATE INDEX IF NOT EXISTS ctgp_client ON ctgp(client);
        CREATE INDEX IF NOT EXISTS ctgp_pid ON ctgp(pid);
        CREATE INDEX IF NOT EXISTS nin_client ON nin(client);
    """)
    return db


def dump_rows(kind,path):
    if kind=='nin':
        # Header includes the 74-byte Mii and its CRC16: never read the full ghost.
        with path.open('rb') as stream:item=parse_mii(stream.read(0x88),str(path))
        match=re.match(r'^(\d+)-',path.name)
        return [(str(path),str(int(match[1])) if match else '',item['avatar'],item['client'],item['name'],'')]
    with path.open(encoding='utf-8-sig') as stream:data=json.load(stream)
    if not isinstance(data,dict):raise ValueError('Expected a CTGP profile JSON object')
    pid=str(data.get('player_id','')).upper()
    if not re.fullmatch('[0-9A-F]{16}',pid):raise ValueError('Invalid CTGP player_id; expected enriched CTGP dump format')
    if re.fullmatch('[0-9a-fA-F]{16}',path.stem) and path.stem.upper()!=pid:raise ValueError('JSON player_id differs from filename')
    items=json_miis(data,pid);rows=[];seen={}
    for item,g in zip(items,data['ghosts']):
        ghost=str(item['ghost'])
        if not re.fullmatch(r'[0-9a-fA-F]{40}\.rkg',ghost,re.I):raise ValueError('Ghost file field must be a 40-hex hash followed by .rkg')
        avatar=item['avatar']
        if avatar and not re.fullmatch('[0-9A-F]{8}',avatar):raise ValueError('Invalid avatar_id')
        row=(str(path),pid,ghost.upper()[:-4]+'.rkg',avatar,item['client'],item['name'],str(g['mii'].get('creator_name') or '').replace('\x00',''))
        if ghost.upper() in seen and seen[ghost.upper()]!=row:raise ValueError('Conflicting duplicate ghost metadata within the profile')
        seen[ghost.upper()]=row
    rows.extend(seen.values());return rows


def scan_dump(db,kind,folder,refresh=False):
    suffix='.json' if kind=='ctgp' else '.rkg'
    print('Listing '+str(folder)+' ('+suffix+')...',flush=True)
    paths=sorted({p.resolve() for p in folder.rglob('*') if p.is_file() and p.suffix.lower()==suffix})
    if not paths:raise ValueError('No '+suffix+' files found in '+str(folder)+'. Extract the dump first.')
    root=str(folder.resolve());setmeta=lambda k,v:db.execute('INSERT OR REPLACE INTO portable_meta VALUES(?,?)',(k,str(v)))
    oldroot=db.execute('SELECT value FROM portable_meta WHERE key=?',('root_'+kind,)).fetchone()
    # An interrupted refresh must be resumed, even if a previously complete cache exists.
    setmeta('complete_'+kind,'0');db.commit()
    seen=set();changed=errors=0;start=time.monotonic()
    try:
        for i,path in enumerate(paths,1):
            key=str(path);seen.add(key)
            try:
                stat=path.stat();old=db.execute('SELECT * FROM portable_files WHERE kind=? AND path=?',(kind,key)).fetchone()
                if old and old['mtime']==stat.st_mtime_ns and old['size']==stat.st_size and not old['error'] and not refresh:
                    pass
                else:
                    rows=dump_rows(kind,path)
                    after=path.stat()
                    if (after.st_mtime_ns,after.st_size)!=(stat.st_mtime_ns,stat.st_size):raise ValueError('File changed during indexing; retry after it finishes copying')
                    db.execute('DELETE FROM '+kind+' WHERE path=?',(key,))
                    if rows:db.executemany('INSERT INTO '+kind+' VALUES('+','.join('?' for _ in rows[0])+')',rows)
                    db.execute('INSERT OR REPLACE INTO portable_files VALUES(?,?,?,?,NULL)',(kind,key,stat.st_mtime_ns,stat.st_size));changed+=1
            except (OSError,ValueError,TypeError,AttributeError,KeyError) as exc:
                # Never retain outdated rows from a now invalid input file.
                db.execute('DELETE FROM '+kind+' WHERE path=?',(key,))
                db.execute('INSERT OR REPLACE INTO portable_files VALUES(?,?,?,?,?)',(kind,key,0,0,str(exc)));changed+=1;errors+=1
            if i%100==0:db.commit()
            if i%500==0 or i==len(paths):
                elapsed=time.monotonic()-start;eta=elapsed/i*(len(paths)-i)
                print(f'  {kind}: {i:,}/{len(paths):,} | parsed {changed:,} | errors {errors:,} | elapsed {elapsed/60:.1f}m | ETA {eta/60:.1f}m',flush=True)
        # Remove disappeared files only after a full, successful directory listing/scan.
        stale=[r[0] for r in db.execute('SELECT path FROM portable_files WHERE kind=?',(kind,)) if r[0] not in seen]
        for key in stale:
            db.execute('DELETE FROM '+kind+' WHERE path=?',(key,));db.execute('DELETE FROM portable_files WHERE kind=? AND path=?',(kind,key))
        setmeta('root_'+kind,root);setmeta('complete_'+kind,'1');db.commit()
    finally:db.commit()


def prepare_dump_index(args):
    explicit=getattr(args,'index',None)
    if explicit is not None:
        if not explicit.is_file():raise ValueError('--index does not exist. Omit --index to build automatically from the dumps.')
        print('Using supplied comparison index read-only: '+str(explicit),flush=True)
        return explicit
    cachefile=args.cache/'dump_index.sqlite3'
    available=[(kind,folder) for kind,folder in [('ctgp',args.ctgp_dir),('nin',args.ninrankings_dir)] if folder.is_dir()]
    if not available and not cachefile.is_file():
        legacy=Path('mii_identity_matches/index.sqlite3')
        if legacy.is_file() and not args.refresh_index:
            print('Using existing MiiConnect24 index read-only: '+str(legacy));return legacy
        print('No comparison dumps/cache found. Supply --ctgp-dir and/or --ninrankings-dir to enable comparisons.')
        return None
    with dump_index_lock(args.cache):
        db=open_dump_index(cachefile)
        try:
            meta=dict(db.execute('SELECT key,value FROM portable_meta'))
            if args.refresh_index and not available:raise ValueError('--refresh-index needs at least one available dump folder')
            for kind,folder in available:
                root=str(folder.resolve())
                if args.refresh_index or meta.get('complete_'+kind)!='1' or meta.get('root_'+kind)!=root:
                    # Fingerprints reuse unchanged files; --reparse-index forces binary/JSON decoding.
                    scan_dump(db,kind,folder,getattr(args,'reparse_index',False))
                else:print('  Reusing '+kind+' comparison cache. Added/changed/removed files? Use --refresh-index.',flush=True)
            for kind in ('ctgp','nin'):
                count=db.execute('SELECT COUNT(*) FROM '+kind).fetchone()[0]
                complete=db.execute('SELECT value FROM portable_meta WHERE key=?',('complete_'+kind,)).fetchone()
                print(f'  Indexed {kind}: {count:,} ghost rows'+(' (incomplete scan; supply its dump folder to resume)' if complete and complete[0]!='1' else ''),flush=True)
                if not count:print('  '+('CTGP comparisons unavailable; supply --ctgp-dir.' if kind=='ctgp' else 'Ghost Database comparisons unavailable; supply --ninrankings-dir.'),flush=True)
            path=args.cache/'dump_index_errors.csv'
            with path.open('w',encoding='utf-8-sig',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(['source','file','error']);writer.writerows(tuple(r) for r in db.execute('SELECT kind,path,error FROM portable_files WHERE error IS NOT NULL ORDER BY kind,path'))
            errors=db.execute('SELECT COUNT(*) FROM portable_files WHERE error IS NOT NULL').fetchone()[0]
            if errors:print(f'WARNING: {errors:,} files excluded; see {path}. Fix them and run --refresh-index.',flush=True)
            print('Comparison cache: '+str(cachefile.resolve()),flush=True)
        finally:db.close()
    return cachefile

def connect(path):
    if not path.is_file():return None
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'ctgp','nin'}.issubset(tables):db.close();raise ValueError('Index is not a MiiConnect24 CTGP/NinRankings index')
    db.create_function('useful_mii',1,useful,deterministic=True)
    print('Loading default-Mii exclusions from the existing index...',flush=True)
    db.execute('CREATE TEMP TABLE blocked(client TEXT PRIMARY KEY)')
    db.execute("INSERT OR IGNORE INTO blocked SELECT client FROM (SELECT DISTINCT client,name FROM ctgp) WHERE useful_mii(name)=0 UNION SELECT client FROM (SELECT DISTINCT client,name FROM nin) WHERE useful_mii(name)=0")
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
        print('Ghost Database profile: '+ghost_database_profile_url(client))
        avatars={x['avatar'] for x in items if x['avatar'] and x['avatar'] not in BAD}
        if any(item['name'] for item in items):
            print('MIIS READ FROM YOUR INPUT:');show_miis(items,set())
        else:print('Client ID entered manually; no specific Mii/avatar supplied.')
        top=(top_matches or {}).get(client,{})
        visible={pid:rows for pid,rows in top.items() if pid!=exclude_nin_pid}
        print('\nMATCHING NINRANKINGS TOP1000 PROFILES:',len(visible))
        for pid,rows in sorted(visible.items()):
            print('  https://ninrankings.org/mkwii/profil.php?id='+pid)
            print('  Friend code: '+top1000_friend_code(pid)+' | Top1000 online PID: '+pid)
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
            pid=mapped[0] if mapped and mapped[0] else str(int(client,16))
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
    p.add_argument('--index',type=Path,help='Optional existing MiiConnect24 index, used read-only; otherwise build/reuse cache from dumps')
    p.add_argument('--ninrankings-dir',type=Path,default=Path('ninrankings'),help='Extracted NinRankings Ghost Database .rkg folder')
    p.add_argument('--refresh-index',action='store_true',help='Rescan dumps for new/changed/removed files; unchanged files reuse cached rows')
    p.add_argument('--reparse-index',action='store_true',help='Reparse every dump file; implies --refresh-index')
    p.add_argument('--index-only',action='store_true',help='Build/check the comparison cache and exit without the menu')
    p.add_argument('--ctgp-dir',type=Path,default=Path('ctgp_profiles'))
    p.add_argument('--identities',type=Path)
    p.add_argument('--nin-pids-json',type=Path,default=Path('ninrankings_pids.json'),help='Local PID -> Mii-name-list JSON')
    p.add_argument('--mii-dir',type=Path,default=Path('miis'),help='Local Wii Mii files, named as in the PID JSON (default miis)')
    p.add_argument('--cache',type=Path,default=Path('mii_client_check_cache'))
    args=p.parse_args()
    if args.reparse_index:args.refresh_index=True
    if args.index and (args.refresh_index or args.reparse_index):p.error('A supplied --index is read-only; omit --index to refresh Portable’s own cache')
    print('MiiConnect24 Portable',flush=True)
    index_path=prepare_dump_index(args)
    if args.index_only:
        if index_path is None:raise ValueError('Nothing to index. Supply extracted dump folders.')
        return
    known=owners(args.identities);db=connect(index_path) if index_path else None
    if db is None:print('No comparison index loaded. Input IDs and local Top1000 comparisons remain available.')
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
