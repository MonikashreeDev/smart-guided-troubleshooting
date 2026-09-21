from __future__ import annotations
import math,re
from collections import Counter
TOKEN=re.compile(r"[a-z0-9]+")
SYN={'laggy':'slow','lags':'slow','sluggish':'slow','software':'update','upgrade':'update','draining':'drain','dies':'drain','photos':'camera','picture':'camera','dim':'dark'}
def tokens(text): return [SYN.get(x,x) for x in TOKEN.findall(text.lower())]
def charvec(text,n=3):
    s=' '.join(tokens(text)); c=Counter(s[i:i+n] for i in range(max(0,len(s)-n+1))); z=math.sqrt(sum(v*v for v in c.values())) or 1
    return {k:v/z for k,v in c.items()}
def cosine(a,b):
    if len(a)>len(b): a,b=b,a
    return sum(v*b.get(k,0) for k,v in a.items())
class HybridIndex:
    def __init__(self,docs,text_fn):
        self.docs=docs; self.texts=[text_fn(d) for d in docs]; self.toks=[tokens(x) for x in self.texts]; self.vecs=[charvec(x) for x in self.texts]
        self.df=Counter(); [self.df.update(set(t)) for t in self.toks]; self.avg=sum(map(len,self.toks))/max(1,len(self.toks)); self.N=len(docs)
    def search(self,q,k=3):
        qt=tokens(q); qv=charvec(q); out=[]
        for d,dt,dv in zip(self.docs,self.toks,self.vecs):
            tf=Counter(dt); bm=0
            for term in qt:
                if not tf[term]: continue
                idf=math.log(1+(self.N-self.df[term]+.5)/(self.df[term]+.5)); den=tf[term]+1.5*(.25+.75*len(dt)/(self.avg or 1)); bm+=idf*tf[term]*2.5/den
            lexical=1-math.exp(-bm/max(1,len(set(qt))))
            dense=cosine(qv,dv)
            score=.62*lexical+.38*dense
            out.append({'doc':d,'score':round(score,4),'lexical':round(lexical,4),'dense':round(dense,4)})
        return sorted(out,key=lambda x:x['score'],reverse=True)[:k]
