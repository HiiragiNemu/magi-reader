#!/usr/bin/env python3
from __future__ import annotations
import argparse, collections, hashlib, json, re
from pathlib import Path
KANA=re.compile(r'[\u3040-\u30ff]'); CJK=re.compile(r'[\u3400-\u9fff]'); NUM=re.compile(r'^\d{4,}$')
TEXT={'talk','narration','charactertalk','onlytext'}
BAD=re.compile(r'(?:＆|&|みんな|一同|の声|声$|男|女|店員|生徒|教師|人々|客|少女|少年|母$|父$|係|スタッフ|住民|敵|謎|不審|工場|館長|子供|子ども|おば|おじ|女子|男子|ナレーション)')
def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def rows(doc):
 for si,sh in enumerate(doc.get('sheetList',[]) if isinstance(doc,dict) else []):
  if not isinstance(sh,dict): continue
  h=sh.get('headerRow',{}).get('cellList',[]); idx={str(v).strip().casefold():i for i,v in enumerate(h)}
  if 'actiontype' not in idx: continue
  for r in sh.get('contentRowList',[]):
   c=r.get('cellList') if isinstance(r,dict) else None
   if isinstance(c,list): yield si,r,c,idx
def text_rows(doc):
 for si,r,c,idx in rows(doc):
  ai,ci=idx['actiontype'],idx.get('comment'); ni=idx.get('name')
  if ci is None: continue
  act=str(c[ai] if ai<len(c) else '').strip().casefold(); com=c[ci] if ci<len(c) else ''
  if act in TEXT and isinstance(com,str) and com.strip():
   yield si,r,c,idx,act,str(c[ni] if ni is not None and ni<len(c) else '')
def functional_hash(doc):
 d=json.loads(json.dumps(doc,ensure_ascii=False)); d['bookTitle']=''
 for _,_,c,idx in rows(d):
  for field in ('name','comment'):
   i=idx.get(field)
   if i is not None and i<len(c): c[i]=''
 return hashlib.sha256(json.dumps(d,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1<<20),b''): h.update(block)
 return h.hexdigest()
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,required=True); ap.add_argument('--archive',type=Path,required=True); ap.add_argument('--out',type=Path,required=True); a=ap.parse_args()
 by_asset=collections.defaultdict(collections.Counter); jp_asset=collections.defaultdict(collections.Counter)
 name_table=[]; name_index={}; entries=[]
 for p in sorted(a.root.rglob('*.json')):
  d=load(p); speakers=[]
  for _,_,c,idx,_,name in text_rows(d):
   if name not in name_index: name_index[name]=len(name_table); name_table.append(name)
   speakers.append(name_index[name])
  for _,_,c,idx in rows(d):
   ni,ai=idx.get('name'),idx.get('assetid')
   if ni is None or ai is None or ni>=len(c) or ai>=len(c): continue
   n,asset=c[ni],c[ai]
   if not isinstance(n,str) or not isinstance(asset,str): continue
   n=n.strip(); asset=asset.strip()
   if not n or not NUM.fullmatch(asset): continue
   if KANA.search(n): jp_asset[asset][n]+=1
   elif CJK.search(n): by_asset[asset][n]+=1
  entries.append({'path':p.relative_to(a.root).as_posix(),'functionalSha256':functional_hash(d),'speakers':speakers})
 choices=collections.defaultdict(collections.Counter)
 for asset,jps in jp_asset.items():
  cns=by_asset.get(asset)
  if not cns: continue
  total=sum(cns.values()); cn,count=cns.most_common(1)[0]
  if count/total < .90: continue
  for jp,n in jps.items(): choices[jp][cn]+=n
 name_map={}
 for jp,vals in choices.items():
  total=sum(vals.values()); cn,count=vals.most_common(1)[0]
  if count/total >= .95 and not BAD.search(jp): name_map[jp]=cn
 name_map.update({'キュゥべえ':'丘比','キュぅべえ':'丘比','アリナ・グレイ':'阿莉娜·格雷'})
 obj={'schemaVersion':2,'sourceArchiveSha256':digest(a.archive),'fileCount':len(entries),'speakerTable':name_table,'files':entries,'nameMap':name_map}
 a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
 print(json.dumps({'fileCount':len(entries),'speakerNames':len(name_table),'nameMappings':len(name_map),'bytes':a.out.stat().st_size},ensure_ascii=False))
if __name__=='__main__': main()
