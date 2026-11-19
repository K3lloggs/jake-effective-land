const DEFAULTS={ppu:20000,lienPpu:12000,openPct:70,rule:'base',sender:'',phone:'',email:''};
function unitsFor(a,rule){
  if(!a||a<360)return 0;
  if(rule==='overlay'){ if(a<1440)return Math.min(2,Math.floor(a/360)); if(a<1920)return 3; return 3+Math.floor((a-1919)/480); }
  return Math.floor(Math.min(a,1440)/360)+Math.floor(Math.max(a-1440,0)/480);
}
function r500(x){return Math.round(x/500)*500;}
function scoreParcel(p,st,S){
  const lien=(st&&st.lien!=null)?!!st.lien:!!p.lien, units=unitsFor(p.area,S.rule), ppu=lien?S.lienPpu:S.ppu, ceiling=units*ppu;
  const why=[];
  // 1 unit fit
  const UF={0:0,1:3,2:10,3:22,4:30,5:24,6:20};
  const fit=units in UF?UF[units]:(units<=8?16:12);
  why.push({k:'Unit fit',pts:fit,max:30,t:units===4?'4 units by right. Sweet spot.':units===0?'Too small for a unit':units+' unit'+(units>1?'s':'')+' by right'});
  // 2 price
  let price,pt;
  if(!p.mv){price=12;pt='No OPA value on record';}
  else{const r=ceiling/p.mv;price=Math.round(Math.max(0,Math.min(1,(r-0.3)/0.7))*30);pt='Ceiling is '+Math.round(r*100)+'% of OPA value';}
  why.push({k:'Price reach',pts:price,max:30,t:pt});
  // 3 seller
  let s=0;const sr=[];
  if(p.hold==null){s+=6;sr.push('no sale on record');}
  else if(p.hold>=20){s+=10;sr.push('held '+Math.round(p.hold)+' yrs');}
  else if(p.hold>=10){s+=8;sr.push('held '+Math.round(p.hold)+' yrs');}
  else if(p.hold>=5){s+=5;sr.push('held '+Math.round(p.hold)+' yrs');}
  else if(p.hold>=2){s+=2;sr.push('held '+Math.round(p.hold)+' yrs');}
  else sr.push('bought within 2 yrs');
  if(!p.ent){s+=7;sr.push('individual owner');}
  if(p.oos){s+=5;sr.push('out-of-state owner');}else if(p.ooc){s+=3;sr.push('owner outside Philadelphia');}
  if(p.sp!=null&&p.sp<=1000&&p.hold>=3){s+=3;sr.push('nominal last transfer');}
  if(lien){s+=8;sr.push('tax lien');}
  let overpaid=false;
  if(p.sp>ceiling&&p.hold!=null&&p.hold<6&&ceiling>0){s-=12;overpaid=true;sr.push('paid $'+Math.round(p.sp/1000)+'k in '+p.sd.slice(0,4)+', above ceiling');}
  s=Math.max(0,Math.min(30,s));
  why.push({k:'Seller likelihood',pts:s,max:30,t:sr.join(', ')});
  // 4 buildability
  let b=0;const br=[];
  if(p.fr>=16){b+=5;br.push(p.fr+' ft frontage');}else if(p.fr>=14){b+=3;br.push(p.fr+' ft frontage, tight');}else if(p.fr){br.push('narrow, '+p.fr+' ft');}else{b+=1;br.push('frontage unknown');}
  if(p.shape==='E'){b+=3;br.push('rectangular');}else if(p.shape==='A'){b+=1.5;br.push('irregular');}else br.push('odd shape');
  if(p.area&&!p.notes.length)b+=2;
  b=Math.round(b);
  why.push({k:'Buildability',pts:b,max:10,t:br.join(', ')});
  let total=fit+price+s+b;
  const same=p.adj.some(a=>a.same), any=p.adj.length>0;
  if(same){total+=4;why.push({k:'Assemblage',pts:4,max:4,t:'Next-door lot has the same owner'});}
  else if(any){total+=2;why.push({k:'Assemblage',pts:2,max:4,t:'Next-door lot is also on this list'});}
  const tags=[];
  if(p.pub)tags.push('Public owner');else if(p.exempt){tags.push('Tax-exempt owner');total-=10;}
  if(lien)tags.push('Tax lien');
  if(overpaid)tags.push('Recent buyer');
  if(same)tags.push('Assemblage');
  if(p.pub)total=Math.min(total,20);
  if(units===0)total=Math.min(total,15);
  total=Math.max(0,Math.min(100,Math.round(total)));
  const tier=p.pub?'P':total>=72?'A':total>=58?'B':total>=42?'C':'D';
  const anchor=p.mv>0?Math.min(ceiling,p.mv):ceiling;
  const open=r500(anchor*S.openPct/100);
  const target=Math.max(open,r500(anchor<ceiling?anchor:ceiling*0.9));
  return {units,ppu,ceiling,open,target,walk:ceiling,score:total,tier,why,tags,lien};
}
if(typeof module!=='undefined')module.exports={DEFAULTS,unitsFor,scoreParcel};
