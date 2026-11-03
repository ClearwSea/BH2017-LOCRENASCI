/* Local-only replacement of the original purchase-click telemetry call. */
typedef unsigned int U;
typedef void O;
#define API(v,t) ((t)(b+(v)))
static int equal(O* value,const char* text) {
 if(!value) return 0;
 U n=0;while(text[n]) n++;
 if(*(U*)((char*)value+8)!=n) return 0;
 unsigned short* chars=(unsigned short*)((char*)value+12);
 for(U i=0;i<n;i++) if(chars[i]!=(unsigned char)text[i]) return 0;
 return 1;
}
__attribute__((visibility("hidden"),noinline))
O* local_recharge_icon(U b,O* unused,O* product,O* info) {
 const char* icon=0;
 if(equal(product,"local_hcoin_60")) icon="HardCoinTier1";
 else if(equal(product,"local_hcoin_300")) icon="HardCoinTier5";
 else if(equal(product,"local_hcoin_980")) icon="HardCoinTier10";
 else if(equal(product,"local_hcoin_1980")) icon="HardCoinTier20";
 else if(equal(product,"local_hcoin_3280")) icon="HardCoinTier50";
 else if(equal(product,"local_hcoin_6480")) icon="HardCoinTier60";
 if(icon) return API(0x29549a0,O*(*)(const char*))(icon);
 return API(0xf804ae,O*(*)(O*,O*,O*))(unused,product,info);
}
__attribute__((visibility("hidden"),noinline))
void local_recharge_click(U b,O* network,O* price,O* currency,O* product,O* info) {
 (void)price; (void)currency; (void)info;
 if(!network || !product) return;
 /* Only authored offline products can enter this path. */
 const char* prefix="local_hcoin_";
 if(*(U*)((char*)product+8)<12) return;
 unsigned short* text=(unsigned short*)((char*)product+12);
 for(U i=0;i<12;i++) if(text[i]!=(unsigned char)prefix[i]) return;
 O* domain=API(0x29538a0,O*(*)(void))(); U n=0;
 O** all=API(0x2953900,O**(*)(O*,U*))(domain,&n);
 if(!all || n>1024) return;
 O* k=0;
 for(U i=0;i<n && !k;i++) {
  O* image=API(0x2952c20,O*(*)(O*))(all[i]);
  k=API(0x2952e00,O*(*)(O*,const char*,const char*))(image,"System","Guid");
 }
 if(!k) return;
 O* make=API(0x2952ff0,O*(*)(O*,const char*,int))(k,"NewGuid",0);
 O* format=API(0x2952ff0,O*(*)(O*,const char*,int))(k,"ToString",0);
 if(!make || !format) return;
 O* ex=0;
 O* boxed=API(0x29547b0,O*(*)(O*,O*,void**,O**))(make,0,0,&ex);
 if(!boxed || ex) return;
 O* value=API(0x2954580,O*(*)(O*))(boxed);
 O* nonce=API(0x29547b0,O*(*)(O*,O*,void**,O**))(format,value,0,&ex);
 if(!nonce || ex) return;
 O* cny=API(0x29549a0,O*(*)(const char*))("CNY");
 if(!cny) return;
 API(0x1167377,void(*)(O*,O*,O*,O*,O*))(network,nonce,cny,product,0);
}
