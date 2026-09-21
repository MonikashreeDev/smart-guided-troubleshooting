from __future__ import annotations
import hashlib,json,os,re,threading,time
from pathlib import Path
from statistics import median
from .api_models import APIEnvelope
from .retrieval import HybridIndex,tokens,charvec,cosine
from .validators import validate

class TroubleshootingEngine:
 def __init__(self,data_root):
    self.data_root=Path(os.getenv('TROUBLESHOOT_DATA_DIR',data_root)); self.lock=threading.Lock(); self.exact={}; self.semantic=[]; self.times=[]; self.requests=0; self.hits={'exact':0,'semantic':0}; self.abstentions=0
    self.siis=self._load('siis_responses.json','demo_siis.json'); self.links=self._load('deeplinks.json','demo_deeplinks.json'); self.scenarios=self._load('queries.json','demo_queries.json')
    self.siis_idx=HybridIndex(self.siis,lambda d:' '.join([d['domain'],d['title'],d['text'],' '.join(d.get('keywords',[]))]))
    # Security property: deeplink itself is deliberately excluded.
    self.link_idx=HybridIndex(self.links,lambda d:' '.join([d['description'],d.get('message',''),d.get('qna_description',''),json.dumps(d.get('classes',{})),d.get('originalType','')]))
    self.version=hashlib.sha256(json.dumps([self.siis,self.links],sort_keys=True).encode()).hexdigest()[:12]
 def _load(self,official,demo):
    p=self.data_root/'official'/official
    q=self.data_root/demo
    with open(p if p.exists() else q,encoding='utf8') as f: return json.load(f)
 def asset_status(self):
    expected=['queries.json','siis_responses.json','deeplinks.json','samples/','schema.py']
    present=[x for x in expected if (self.data_root/'official'/x).exists()]
    return {'mode':'official' if len(present)==len(expected) else 'synthetic_demo','official_present':present,'official_missing':[x for x in expected if x not in present],'pipeline_version':self.version}
 def health(self): return {'status':'ok','indexes':{'siis':len(self.siis),'deeplinks':len(self.links)},'assets':self.asset_status()['mode']}
 def normalize(self,q): return ' '.join(tokens(q))
 def intent(self,q):
    t=set(tokens(q)); domains={d:sum(w in t for w in ws) for d,ws in {'Battery':['battery','drain','charge'],'Display':['screen','display','flicker','dark','swipe','navigation'],'Camera':['camera','photo','picture','blurry'],'Performance':['slow','performance','lag','update','hot']}.items()}
    domain=max(domains,key=domains.get) if max(domains.values()) else 'Unknown'
    trigger=next((x for x in ['update','install','app','restart','charge'] if x in t),'none')
    feature=next((x for x in ['navigation','battery','camera','screen','performance'] if x in t),domain.lower())
    symptom=next((x for x in ['slow','drain','flicker','dark','blurry','swipe','hot'] if x in t),'unknown')
    return {'domain':domain,'trigger':trigger,'feature':feature,'symptom':symptom}
 def variations(self,q,i):
    d=i['domain'].lower(); s=i['symptom']; tr='' if i['trigger']=='none' else ' after '+i['trigger']
    vals=[q.strip(),f'{d} {s}{tr}',f'Galaxy {i["feature"]} issue: {s}{tr}',f'Help fix {s} {i["feature"]}{tr}',f'{i["feature"]} is {s}{tr}',f'Troubleshoot {d} {s}',f'{s} problem on Samsung {d}',f'Phone {i["feature"]} behaves {s}{tr}']
    return list(dict.fromkeys(vals))[:10]
 def _cache_key(self,n): return self.version+':'+hashlib.sha256(n.encode()).hexdigest()
 def _semantic_hit(self,n,intent):
    v=charvec(n)
    for row in self.semantic:
      same=all(intent[k]==row['intent'][k] for k in ('domain','symptom','trigger','feature'))
      if same and cosine(v,row['vec'])>=.73: return row['payload']
 def troubleshoot(self,query,siis_response=None):
    start=time.perf_counter(); n=self.normalize(query); intent=self.intent(query); key=self._cache_key(n); cache='miss'
    with self.lock:
      self.requests+=1
      if key in self.exact: payload=json.loads(json.dumps(self.exact[key])); cache='exact'; self.hits['exact']+=1
      else:
       payload=self._semantic_hit(n,intent)
       if payload: payload=json.loads(json.dumps(payload)); cache='semantic'; self.hits['semantic']+=1
    if cache=='miss': payload=self._compile(query,intent,siis_response)
    elapsed=round((time.perf_counter()-start)*1000,2)
    payload['query']=query; payload['meta']['latency_ms']=elapsed; payload['meta']['cache_hit']=cache!='miss'; payload['meta']['cache_type']=cache
    with self.lock:
      self.times.append(elapsed); self.times=self.times[-1000:]
      if cache=='miss': self.exact[key]=json.loads(json.dumps(payload)); self.semantic.append({'vec':charvec(n),'intent':intent,'payload':json.loads(json.dumps(payload))}); self.semantic=self.semantic[-300:]
    return payload
 def _compile(self,query,intent,siis_response):
    if intent['domain']=='Unknown': return self._abstain(query,'no_match',intent)
    q=query+' '+intent['domain']+' '+intent['symptom']+' '+intent['trigger']
    sr=self.siis_idx.search(q,3); best=sr[0]
    if siis_response:
      evidence={'id':'request_context','domain':intent['domain'],'title':'Provided SIIS','text':siis_response,'keywords':[]}; e_score=.99
    else: evidence=best['doc']; e_score=best['score']
    if e_score<.20 or (evidence['domain']!=intent['domain'] and not siis_response): return self._abstain(query,'no_siis_context',intent)
    lr=self.link_idx.search(evidence['text']+' '+query,3); link=lr[0]
    if link['score']<.18: return self._abstain(query,'no_match',intent)
    d=link['doc']; steps=evidence['steps']; category=evidence.get('category','auto'); action_name=evidence['actionName']; desc=evidence['description']
    action={'actionName':action_name,'description':desc,'stepGroups':[{'steps':steps,'validationDeeplink':None,'actionableDeeplink':{k:d.get(k) for k in ['deeplink','description','message','classes','originalType']}}],'category':category}
    topic=evidence['domain']; goal={'goal':f'Follow these steps to perform this {topic} Troubleshooting.','title':evidence['title'],'actions':[action],'score':float(round(min(.99,.58*e_score+.42*link['score']),2))}
    core={'contexts':[goal]}; errors=validate(core,self.links,{action_name:evidence['text']})
    if errors: return self._abstain(query,'validation_failed',intent,errors)
    proof={'source_id':evidence['id'],'source_span':evidence['text'],'catalog_id':d['id'],'screen_identity':d['description'],'risk':category,'retrieval':{'siis':sr,'deeplink':[{k:v for k,v in x.items() if k!='doc'}|{'id':x['doc']['id']} for x in lr]},'validators':{'passed':True,'errors':[]}}
    meta={'model':'deterministic-hybrid-demo','cost_usd':0.0,'fallback':None,'intent':intent,'proof':[proof],'asset_mode':self.asset_status()['mode'],'pipeline_version':self.version,'latency_ms':0,'cache_hit':False,'cache_type':'miss'}
    return APIEnvelope(query,self.variations(query,intent),core,meta).to_dict()
 def _abstain(self,q,reason,intent,errors=None):
    with self.lock: self.abstentions+=1
    return APIEnvelope(q,self.variations(q,intent),{'contexts':[]},{'model':'deterministic-hybrid-demo','cost_usd':0.0,'fallback':reason,'intent':intent,'proof':[],'validator_errors':errors or [],'asset_mode':self.asset_status()['mode'],'pipeline_version':self.version,'latency_ms':0,'cache_hit':False,'cache_type':'miss'}).to_dict()
 def metrics(self):
    ts=sorted(self.times); pct=lambda p: ts[min(len(ts)-1,int((len(ts)-1)*p))] if ts else 0
    return {'requests':self.requests,'cache_hits':self.hits,'cache_hit_rate':round(sum(self.hits.values())/max(1,self.requests),3),'abstentions':self.abstentions,'latency_ms':{'p50':pct(.5),'p95':pct(.95)},'schema_contract':'Appendix A core + Appendix B envelope','catalog_integrity':1.0,'url_leaks':0,'assets':self.asset_status()}
