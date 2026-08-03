#!/usr/bin/env python3
from __future__ import annotations
import argparse, collections, hashlib, json, re, shutil, subprocess
from pathlib import Path
from typing import Any
from opencc import OpenCC

TEXT={"talk","narration","charactertalk","onlytext"}
KANA=re.compile(r'[\u3040-\u30ff]')
TITLE={
 '魔法少女ストーリー':'魔法少女剧情','イベントストーリー':'活动剧情',
 'メインストーリー':'主线剧情','VSイベント':'VS活动',
 'ポートレイトストーリー':'肖像剧情','フラッシュバック演出後会話':'闪回演出后对话',
 '断片シナリオ':'片段剧情','記憶の窓解放':'记忆之窗解锁','機能解放':'功能解锁','ガチャ':'抽卡'
}

def load(p:Path): return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p:Path,x:Any,indent=2): p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=indent)+'\n',encoding='utf-8')
def sha(p:Path):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def rows(doc):
 for si,sh in enumerate(doc.get('sheetList',[]) if isinstance(doc,dict) else []):
  if not isinstance(sh,dict):continue
  h=sh.get('headerRow',{}).get('cellList',[]);idx={str(v).strip().casefold():i for i,v in enumerate(h)}
  if 'actiontype' not in idx:continue
  for r in sh.get('contentRowList',[]):
   c=r.get('cellList') if isinstance(r,dict) else None
   if isinstance(c,list):yield si,r,c,idx
def textrefs(doc):
 out=[]
 for si,r,c,idx in rows(doc):
  ai,ci=idx['actiontype'],idx.get('comment');ni=idx.get('name')
  if ci is None:continue
  act=str(c[ai] if ai<len(c) else '').strip().casefold();com=c[ci] if ci<len(c) else ''
  if act in TEXT and isinstance(com,str) and com.strip():out.append((si,r,c,idx,act,ci,ni))
 return out
def fhash(doc):
 d=json.loads(json.dumps(doc,ensure_ascii=False));d['bookTitle']=''
 for _,_,c,idx in rows(d):
  for k in ('name','comment'):
   i=idx.get(k)
   if i is not None and i<len(c):c[i]=''
 return hashlib.sha256(json.dumps(d,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def conv(x,cc,stats,name_map):
 if isinstance(x,str):
  old=x
  if x in name_map:x=name_map[x]
  elif '/' in x:
   a,b=x.split('/',1)
   if a in name_map:x=name_map[a]+'/'+b
  x=cc.convert(x)
  for a,b in TITLE.items():x=x.replace(a,b)
  if x!=old:stats['convertedStrings']+=1
  return x
 if isinstance(x,list):return [conv(v,cc,stats,name_map) for v in x]
 if isinstance(x,dict):return {k:conv(v,cc,stats,name_map) for k,v in x.items()}
 return x

def build_scenarios(repo:Path,inv:dict,out:Path,cc,stats):
 root=repo/'magiraexedra-translate-data-master'/'Scenarios_full'
 index=collections.defaultdict(list)
 for p in root.rglob('*.json'):
  if p.name.endswith(('.provenance.json','.import-report.json')):continue
  try:cat=p.relative_to(root).parts[0]
  except:continue
  index[(cat.casefold(),p.name.casefold())].append(p)
 table=inv['speakerTable']; unresolved=[]
 for item in inv['files']:
  rel=Path(item['path']);key=(rel.parts[0].casefold(),rel.name.casefold())
  matches=[]
  for p in index.get(key,[]):
   try:d=load(p)
   except:continue
   if fhash(d)==item['functionalSha256']:matches.append((p,d))
  if len(matches)!=1:raise RuntimeError(f'唯一结构匹配失败: {rel}: {len(matches)}')
  p,d=matches[0];refs=textrefs(d);speakers=item['speakers']
  if len(refs)!=len(speakers):raise RuntimeError(f'说话人事件数不一致: {rel}')
  for ref,nidx in zip(refs,speakers):
   ni=ref[6]
   if ni is not None:
    c=ref[2]
    while len(c)<=ni:c.append('')
    c[ni]=table[nidx]
  d=conv(d,cc,stats,inv['nameMap'])
  dest=out/rel;save(dest,d,2);stats['scenarioFiles']+=1
  for ref in textrefs(d):
   text=str(ref[2][ref[5]])
   name=str(ref[2][ref[6]]) if ref[6] is not None and ref[6]<len(ref[2]) else ''
   if KANA.search(text):
    stats['japaneseTextRows']+=1
    if len(unresolved)<200:unresolved.append({'file':rel.as_posix(),'row':ref[1].get('rowNumber'),'text':text[:240]})
   if KANA.search(name):stats['japaneseSpeakerRows']+=1
 stats['unresolvedJapaneseSamples']=unresolved

def build_manifests(src:Path,out:Path,cc,stats):
 subprocess.run(['7z','x','-y',f'-o{out}',str(src)],check=True)
 for p in out.rglob('*'):
  if not p.is_file():continue
  stats['manifestFiles']+=1
  if p.suffix.lower()=='.json':
   d=conv(load(p),cc,stats,{})
   save(p,d,2);stats['manifestJsonFiles']+=1
  elif p.suffix.lower() in {'.txt','.md','.csv','.m3u8'}:
   try:s=p.read_text(encoding='utf-8-sig')
   except UnicodeDecodeError:continue
   p.write_text(cc.convert(s),encoding='utf-8')
def arc(src:Path,dst:Path):
 subprocess.run(['7z','a','-t7z','-mx=9','-m0=lzma2','-ms=on',str(dst),'.'],cwd=src,check=True)
 subprocess.run(['7z','t',str(dst)],check=True)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--inventory',type=Path,required=True);ap.add_argument('--manifests',type=Path,required=True);ap.add_argument('--work',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 inv=load(a.inventory)
 if inv.get('schemaVersion')!=2 or inv.get('fileCount')!=2780:raise RuntimeError('inventory invalid')
 shutil.rmtree(a.work,ignore_errors=True);shutil.rmtree(a.out,ignore_errors=True)
 sr=a.work/'Scenarios';mr=a.work/'Manifests';sr.mkdir(parents=True);mr.mkdir(parents=True);a.out.mkdir(parents=True)
 stats=collections.defaultdict(int);cc=OpenCC('tw2sp')
 build_scenarios(a.repo,inv,sr,cc,stats);build_manifests(a.manifests,mr,cc,stats)
 if stats['scenarioFiles']!=inv['fileCount']:raise RuntimeError('scenario count mismatch')
 if stats['japaneseTextRows']:
  raise RuntimeError(f"仍有 {stats['japaneseTextRows']} 条日文正文，拒绝发布")
 for p in sr.rglob('*.json'):load(p)
 for p in mr.rglob('*.json'):load(p)
 sa=a.out/'Scenarios.7z';ma=a.out/'Manifests.7z';arc(sr,sa);arc(mr,ma)
 stats['assets']={sa.name:{'bytes':sa.stat().st_size,'sha256':sha(sa)},ma.name:{'bytes':ma.stat().st_size,'sha256':sha(ma)}}
 report=dict(stats);save(a.out/'localization-report.json',report,2)
 (a.out/'SHA256SUMS.txt').write_text(''.join(f"{v['sha256']}  {k}\n" for k,v in sorted(report['assets'].items())),encoding='utf-8')
 notes=['# Latest Data','', '已将台服数据转换为简体中文，并按上传压缩包的 2,780 个剧情文件清单重建。','',f"- 剧情 JSON：{report['scenarioFiles']} 个",f"- 清单文件：{report['manifestFiles']} 个",f"- 日文剧情正文残留：{report['japaneseTextRows']} 条",f"- 日文内部说话人标签：{report['japaneseSpeakerRows']} 条（不影响正文，详见审计报告）",'- 所有剧情候选均通过去除 Name/Comment 后的功能结构 SHA-256 匹配','- 输出压缩包通过 7-Zip 完整性测试，全部 JSON 通过解析校验','','附件：`Scenarios.7z`、`Manifests.7z`、`localization-report.json`、`SHA256SUMS.txt`。']
 (a.out/'RELEASE_NOTES.md').write_text('\n'.join(notes)+'\n',encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
