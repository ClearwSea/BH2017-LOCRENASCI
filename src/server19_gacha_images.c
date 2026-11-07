/* Bounded native 1.9 x86 event poster input; no page or module replacement. */
typedef unsigned int U;
typedef unsigned short H;
typedef void O;
#define NIL ((O*)0)
#define API(v,t) ((t)(b+(v)))
static O* klass(U b,const char* space,const char* name) {
 O* domain=API(0x29538a0,O*(*)(void))(); U n=0;
 O** all=API(0x2953900,O**(*)(O*,U*))(domain,&n);
 if(!all || n>1024) return NIL;
 for(U i=0;i<n;i++) {
  O* image=API(0x2952c20,O*(*)(O*))(all[i]);
  O* k=API(0x2952e00,O*(*)(O*,const char*,const char*))(image,space,name);
  if(k) return k;
 }
 return NIL;
}
static O* invoke(U b,O* k,const char* name,int count,O* object,void** args,O** ex) {
 if(!k || *ex) return NIL;
 O* m=API(0x2952ff0,O*(*)(O*,const char*,int))(k,name,count);
 if(!m) return NIL;
 return API(0x29547b0,O*(*)(O*,O*,void**,O**))(m,object,args,ex);
}
static int equal(O* value,const char* text) {
 if(!value) return 0;
 U n=0; while(text[n]) n++;
 if(*(U*)((char*)value+8)!=n) return 0;
 H* chars=(H*)((char*)value+12);
 for(U i=0;i<n;i++) if(chars[i]!=(H)(unsigned char)text[i]) return 0;
 return 1;
}
__attribute__((visibility("hidden"),noinline))
O* gacha_event_sprite(U b,O* unused,O* path,U flag,O* info,O* image) {
 /* Existing resource lookup retains priority and its exact four-arg ABI. */
 O* original=API(0x268673e,O*(*)(O*,O*,U,O*))(unused,path,flag,info);
 if(original) return original;
 const char* file=NIL;
 if(equal(path,"Server19/Gacha/Ziyuan")) file="./data/bh3-server19-resources/gacha/ziyuan.png";
 else if(equal(path,"Server19/Gacha/Dracula")) file="./data/bh3-server19-resources/gacha/dracula.png";
 else if(equal(path,"Server19/Bridge/Github")) file="./data/bh3-server19-resources/bridge/github.png";
 else if(equal(path,"Server19/Bridge/Celebration")) file="./data/bh3-server19-resources/bridge/celebration.png";
 else if(equal(path,"Server19/Announcement/TeaParty")) file="./data/bh3-server19-resources/announcement/teaparty.png";
 else if(equal(path,"Server19/Announcement/Update")) file="./data/bh3-server19-resources/announcement/update.png";
 else return NIL;
 /* Stock Pic stretches to its parent plus 194.578125 height, then the parent
  * mask clips the banner. Only these two authored posters fill the actual
  * viewport; Image preserves aspect instead of stretching subject geometry.
  * Input is the Image already resolved by SetupSpecial/CustomTab. */
 if(image && (equal(path,"Server19/Gacha/Ziyuan") || equal(path,"Server19/Gacha/Dracula"))) {
  /* Pic also has stock AspectRatioFitter mode4 (EnvelopeParent), ratio2.45.
   * Disable only that component on these event images before sizing them. */
  O* fitter_class=klass(b,"UnityEngine.UI","AspectRatioFitter");
  if(fitter_class) {
   O* type=API(0x29532a0,O*(*)(O*))(fitter_class);
   O* type_object=API(0x2954db0,O*(*)(O*))(type);
   O* fitter=API(0x224e0d2,O*(*)(O*,O*,O*))(image,type_object,NIL);
   if(fitter) API(0x21dc594,void(*)(O*,U,O*))(fitter,0,NIL);
  }
  O* rect=API(0x21ec3eb,O*(*)(O*,O*))(image,NIL);
  if(rect) API(0x22970c0,void(*)(O*,float,float,O*))(rect,0.0f,0.0f,NIL);
  API(0x21f4b1f,void(*)(O*,U,O*))(image,1,NIL);
 }
 /* Bridge banners keep their original RectTransform and layout components. */
 if(image && (equal(path,"Server19/Bridge/Github") || equal(path,"Server19/Bridge/Celebration") ||
              equal(path,"Server19/Announcement/TeaParty") || equal(path,"Server19/Announcement/Update")))
  API(0x21f4b1f,void(*)(O*,U,O*))(image,1,NIL);
 O* ex=NIL;
 O* file_class=klass(b,"System.IO","File");
 O* p=API(0x29549a0,O*(*)(const char*))(file);
 void* fa[1]={p};
 O* exists=invoke(b,file_class,"Exists",1,NIL,fa,&ex);
 if(!exists || ex || !*(unsigned char*)API(0x2954580,void*(*)(O*))(exists)) return NIL;
 O* bytes=invoke(b,file_class,"ReadAllBytes",1,NIL,fa,&ex);
 if(!bytes || ex) return NIL;
 U length=*(U*)((char*)bytes+12);
 if(length<32 || length>8388608) return NIL;
 O* tk=klass(b,"UnityEngine","Texture2D");
 if(!tk) return NIL;
 O* texture=API(0x2954530,O*(*)(O*))(tk);
 if(!texture) return NIL;
 int two=2; void* ca[2]={&two,&two};
 invoke(b,tk,".ctor",2,texture,ca,&ex);
 if(ex) return NIL;
 void* la[1]={bytes};
 O* loaded=invoke(b,tk,"LoadImage",1,texture,la,&ex);
 if(!loaded || ex || !*(unsigned char*)API(0x2954580,void*(*)(O*))(loaded)) return NIL;
 O* parent=klass(b,"UnityEngine","Texture");
 O* wo=invoke(b,parent,"get_width",0,texture,NIL,&ex);
 O* ho=invoke(b,parent,"get_height",0,texture,NIL,&ex);
 if(!wo || !ho || ex) return NIL;
 int w=*(int*)API(0x2954580,void*(*)(O*))(wo), h=*(int*)API(0x2954580,void*(*)(O*))(ho);
 if(w<1 || h<1 || w>4096 || h>4096) return NIL;
 /* Exact stock libunity registration and x86 stack ABI checked by builder:
  * texture, Rect&, Vector2&, pixelsPerUnit, extrude, meshType, Vector4&. */
 typedef O*(*Create)(O*,float*,float*,float,U,int,float*);
 Create create=API(0x29529f0,void*(*)(const char*))("UnityEngine.Sprite::INTERNAL_CALL_Create");
 if(!create) return NIL;
 /* Full bitmap; viewport sizing and aspect preservation handle placement. */
 float rect[4]={0,0,(float)w,(float)h},pivot[2]={0.5f,0.5f},border[4]={0,0,0,0};
 return create(texture,rect,pivot,100.0f,0,0,border);
}
