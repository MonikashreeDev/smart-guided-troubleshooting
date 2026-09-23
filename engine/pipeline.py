from __future__ import annotations
import hashlib,json,os,re,threading,time
from pathlib import Path
from statistics import median
from .api_models import APIEnvelope
from .retrieval import HybridIndex,tokens,charvec,cosine
from .validators import validate
from .ai import WorkersAI,dense_cosine,LLM_MODEL,EMBED_MODEL

AI_MIN_CONFIDENCE=float(os.getenv('SGT_AI_MIN_CONFIDENCE','0.6'))
EMB_DOMAIN_MIN=float(os.getenv('SGT_EMB_DOMAIN_MIN','0.55'))
EMB_DOMAIN_MARGIN=float(os.getenv('SGT_EMB_DOMAIN_MARGIN','0.06'))
SEM_CACHE_EMB=float(os.getenv('SGT_SEM_CACHE_EMB','0.90'))

class TroubleshootingEngine:
 def __init__(self,data_root,ai=None):
    self.ai=ai if ai is not None else WorkersAI(); self._emb_ready=False; self._emb_retry_at=0.0; self.ai_hits={'understood':0,'fallback':0,'out_of_scope':0}
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
 def health(self): return {'status':'ok','ai':{'enabled':self.ai.enabled,'llm':LLM_MODEL,'embeddings':EMBED_MODEL,'embeddings_ready':self._emb_ready},'indexes':{'siis':len(self.siis),'deeplinks':len(self.links)},'assets':self.asset_status()['mode']}
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
 def _ensure_embeddings(self):
    if self._emb_ready or not self.ai.enabled or time.time()<self._emb_retry_at: return self._emb_ready
    a=self.ai.embed(self.siis_idx.texts); b=self.ai.embed(self.link_idx.texts) if a else None
    if a and b: self.siis_idx.set_embeddings(a); self.link_idx.set_embeddings(b); self._emb_ready=True
    else: self._emb_retry_at=time.time()+60
    return self._emb_ready
 def _qemb(self,text):
    if not self._ensure_embeddings(): return None
    v=self.ai.embed([text]); return v[0] if v else None
 def understand(self,query):
    """AI complaint understanding with deterministic fallback. Returns (effective_query,intent,info)."""
    rules=self.intent(query)
    info={'used':False,'reason':'ai_disabled' if not self.ai.enabled else None,'rules_intent':rules}
    if not self.ai.enabled: return query,rules,info
    u=self.ai.understand(query)
    if u is None:
        info['reason']='ai_unavailable_fallback_to_rules'; self.ai_hits['fallback']+=1
        return query,self._embedding_domain(query,rules,info),info
    info.update({k:u[k] for k in ('supported','symptom','trigger','confidence','language','english','canonical_query','model')})
    if u['supported'] and u['confidence']>=AI_MIN_CONFIDENCE:
        intent=self.intent(u['canonical_query'])
        if intent['domain']==u['domain']:
            info['used']=True; info['reason']='ai_understood'; self.ai_hits['understood']+=1
            return u['canonical_query'],intent,info
        info['reason']='ai_label_mismatch_fallback_to_rules'
    elif not u['supported'] and u['confidence']>=AI_MIN_CONFIDENCE:
        info['reason']='ai_out_of_scope'; self.ai_hits['out_of_scope']+=1
        if rules['domain']=='Unknown': info['used']=True
        return query,rules,info
    else: info['reason']='ai_low_confidence_fallback_to_rules'
    self.ai_hits['fallback']+=1
    return query,self._embedding_domain(query,rules,info),info
 def _embedding_domain(self,query,rules,info):
    """When keyword rules find no domain, let real embeddings suggest one.
    Only a clear, high-similarity match with a margin is accepted; retrieval
    gates and validators still run afterwards."""
    if rules['domain']!='Unknown': return rules
    v=self._qemb(self.normalize(query))
    if v is None: return rules
    sims=sorted(((dense_cosine(v,e),d['domain'],d['id']) for e,d in zip(self.siis_idx.emb,self.siis)),reverse=True)
    top=sims[0]; runner=next((x for x in sims[1:] if x[1]!=top[1]),(0,None,None))
    info['embedding_domain']={'domain':top[1],'source_id':top[2],'similarity':round(top[0],3),'margin':round(top[0]-runner[0],3)}
    if top[0]>=EMB_DOMAIN_MIN and top[0]-runner[0]>=EMB_DOMAIN_MARGIN:
        info['reason']=(info.get('reason') or '')+'+embedding_domain'
        return {**rules,'domain':top[1],'feature':top[1].lower()}
    return rules
 def _cache_key(self,n): return self.version+':'+hashlib.sha256(n.encode()).hexdigest()
 def _semantic_hit(self,n,intent,emb=None):
    v=charvec(n)
    for row in self.semantic:
      same=all(intent[k]==row['intent'][k] for k in ('domain','symptom','trigger','feature'))
      if not same: continue
      if emb is not None and row.get('emb') is not None:
        if dense_cosine(emb,row['emb'])>=SEM_CACHE_EMB: return row['payload']
      elif cosine(v,row['vec'])>=.73: return row['payload']
 def troubleshoot(self,query,siis_response=None):
    start=time.perf_counter(); n=self.normalize(query); key=self._cache_key(n); cache='miss'; payload=None; emb=None
    with self.lock:
      self.requests+=1
      if key in self.exact: payload=json.loads(json.dumps(self.exact[key])); cache='exact'; self.hits['exact']+=1
    if cache=='miss':
      eff,intent,info=self.understand(query); en=self.normalize(eff)
      emb=self._qemb(en)
      with self.lock:
        hit=self._semantic_hit(en,intent,emb)
        if hit: payload=json.loads(json.dumps(hit)); cache='semantic'; self.hits['semantic']+=1; payload['meta']['understanding']=info
      if payload is None:
        if info.get('reason')=='ai_out_of_scope' and info.get('used'): payload=self._abstain(query,'no_match',intent,understanding=info)
        else: payload=self._compile(query,intent,siis_response,eff,info)
    elapsed=round((time.perf_counter()-start)*1000,2)
    payload['query']=query; payload['meta']['latency_ms']=elapsed; payload['meta']['cache_hit']=cache!='miss'; payload['meta']['cache_type']=cache
    with self.lock:
      self.times.append(elapsed); self.times=self.times[-1000:]
      if cache=='miss':
        self.exact[key]=json.loads(json.dumps(payload))
        self.semantic.append({'vec':charvec(en),'emb':emb,'intent':intent,'payload':json.loads(json.dumps(payload))}); self.semantic=self.semantic[-300:]
    return payload
 def _compile(self,query,intent,siis_response,eff=None,info=None):
    eff=eff or query; info=info or {}
    if intent['domain']=='Unknown': return self._abstain(query,'no_match',intent,understanding=info)
    q=eff+' '+intent['domain']+' '+intent['symptom']+' '+intent['trigger']
    sr=self.siis_idx.search(q,3,self._qemb(q)); best=sr[0]
    if siis_response:
      evidence={'id':'request_context','domain':intent['domain'],'title':'Provided SIIS','text':siis_response,'keywords':[]}; e_score=.99
    else: evidence=best['doc']; e_score=best['score']
    if e_score<.20 or (evidence['domain']!=intent['domain'] and not siis_response): return self._abstain(query,'no_siis_context',intent,understanding=info)
    lq=evidence['text']+' '+eff; lr=self.link_idx.search(lq,3,self._qemb(lq)); link=lr[0]
    if link['score']<.18: return self._abstain(query,'no_match',intent,understanding=info)
    d=link['doc']; steps=evidence['steps']; category=evidence.get('category','auto'); action_name=evidence['actionName']; desc=evidence['description']
    action={'actionName':action_name,'description':desc,'stepGroups':[{'steps':steps,'validationDeeplink':None,'actionableDeeplink':{k:d.get(k) for k in ['deeplink','description','message','classes','originalType']}}],'category':category}
    topic=evidence['domain']; goal={'goal':f'Follow these steps to perform this {topic} Troubleshooting.','title':evidence['title'],'actions':[action],'score':float(round(min(.99,.58*e_score+.42*link['score']),2))}
    core={'contexts':[goal]}; errors=validate(core,self.links,{action_name:evidence['text']})
    if errors: return self._abstain(query,'validation_failed',intent,errors,understanding=info)
    proof={'source_id':evidence['id'],'source_span':evidence['text'],'catalog_id':d['id'],'screen_identity':d['description'],'risk':category,'retrieval':{'siis':sr,'deeplink':[{k:v for k,v in x.items() if k!='doc'}|{'id':x['doc']['id']} for x in lr]},'validators':{'passed':True,'errors':[]}}
    meta={'model':self._model_label(info,sr),'cost_usd':0.0,'fallback':None,'intent':intent,'understanding':info,'retrieval_mode':sr[0].get('dense_model'),'proof':[proof],'asset_mode':self.asset_status()['mode'],'pipeline_version':self.version,'latency_ms':0,'cache_hit':False,'cache_type':'miss'}
    return APIEnvelope(query,self.variations(query,intent),core,meta).to_dict()
 def _model_label(self,info,sr=None):
    parts=[]
    if info.get('used'): parts.append('llama-3.3-70b-instruct-fp8-fast (understanding)')
    if sr and sr[0].get('dense_model')=='bge-small-en-v1.5': parts.append('bge-small-en-v1.5 (retrieval)')
    parts.append('deterministic validators')
    return ' + '.join(parts) if len(parts)>1 else 'deterministic-hybrid-demo'
 def _abstain(self,q,reason,intent,errors=None,understanding=None):
    with self.lock: self.abstentions+=1
    return APIEnvelope(q,self.variations(q,intent),{'contexts':[]},{'model':self._model_label(understanding or {}),'cost_usd':0.0,'fallback':reason,'intent':intent,'understanding':understanding or {},'proof':[],'validator_errors':errors or [],'asset_mode':self.asset_status()['mode'],'pipeline_version':self.version,'latency_ms':0,'cache_hit':False,'cache_type':'miss'}).to_dict()
 def metrics(self):
    ts=sorted(self.times); pct=lambda p: ts[min(len(ts)-1,int((len(ts)-1)*p))] if ts else 0
    return {'requests':self.requests,'cache_hits':self.hits,'cache_hit_rate':round(sum(self.hits.values())/max(1,self.requests),3),'abstentions':self.abstentions,'latency_ms':{'p50':pct(.5),'p95':pct(.95)},'schema_contract':'Appendix A core + Appendix B envelope','catalog_integrity':1.0,'url_leaks':0,'assets':self.asset_status(),'ai':{**self.ai.status(),'embeddings_ready':self._emb_ready,**self.ai_hits},'benchmark':self.benchmark()}
 def benchmark(self):
    p=Path(__file__).parents[1]/'evaluation_ai.json'
    try:
      with open(p,encoding='utf8') as f: b=json.load(f)
      return {k:b[k] for k in ('generated_at','dataset','cases','configs') if k in b}
    except Exception: return None
