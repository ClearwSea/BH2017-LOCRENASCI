/* Scoped ARM601 input and SP adapters. No replacement UI or global state. */
#include "fuka-api.h"
typedef unsigned int U;
typedef unsigned short H;
typedef void O;
#define FN(n,t) ((t)(b+API_##n))
#define METHOD(n,t) ((t)(b+METHOD_##n))
#define EXPORT __attribute__((visibility("hidden"),noinline))

static O* field(U b,O* obj,const char* name) {
 if(!obj)return 0;
 O* k=FN(object_get_class,O*(*)(O*))(obj);
 return FN(class_get_field_from_name,O*(*)(O*,const char*))(k,name);
}
static O* ref(U b,O* obj,const char* name) {
 O* f=field(b,obj,name);O* v=0;
 if(f)FN(field_get_value,void(*)(O*,O*,void*))(obj,f,&v);
 return v;
}
static U integer(U b,O* obj,const char* name) {
 O* f=field(b,obj,name);U v=0;
 if(f)FN(field_get_value,void(*)(O*,O*,void*))(obj,f,&v);
 return v;
}
static float number(U b,O* obj,const char* name) {
 O* f=field(b,obj,name);float v=0;
 if(f)FN(field_get_value,void(*)(O*,O*,void*))(obj,f,&v);
 return v;
}
static int equal(O* obj,const char* s) {
 if(!obj)return 0;
 U n=0;while(s[n])n++;
 if(*(U*)((char*)obj+8)!=n)return 0;
 H* chars=(H*)((char*)obj+12);
 for(U i=0;i<n;i++)if(chars[i]!=(unsigned char)s[i])return 0;
 return 1;
}
static int fuka(U b,O* actor) {
 return integer(b,ref(b,actor,"avatarDataItem"),"avatarID")==601;
}

/* The converted common mixin retains original OnAdded/OnRemoved hold state.
 * Only601 redirects the two existing ATK hold gates to SKL02. The original
 * TryHold, pointer release, interactability, thresholds and cooldown run on. */
EXPORT U fuka_button_equal(U b,O* dummy,O* left,O* right,O* info,O* button) {
 if(equal(right,"ATK") && fuka(b,ref(b,button,"_avatarActor")))
  return equal(left,"SKL02");
 return METHOD(513,U(*)(O*,O*,O*,O*))(dummy,left,right,info);
}

/* Source ConsumeWithProperty=true for this exact -25 cost applies:
 * (ordinary calculated amount + Actor_SkillSPCostDelta)*(1+ratio).
 * Original target HealSP still performs its own original recovery handling. */
EXPORT float fuka_sp_cost(U b,O* self,O* ability,O* config,O* target,O* info) {
 float amount=METHOD(49409,float(*)(O*,O*,O*,O*,O*))(self,ability,config,target,info);
 if(!fuka(b,target) ||
    !equal(ref(b,ref(b,ability,"config"),"AbilityName"),"Fuka_FK_Cost_SP"))return amount;
 O* dynamic=ref(b,config,"Amount");
 if(integer(b,dynamic,"isDynamic") || number(b,dynamic,"fixedValue")!=-25.0f)return amount;
 O* delta_key=FN(string_new,O*(*)(const char*))("Actor_SkillSPCostDelta");
 O* ratio_key=FN(string_new,O*(*)(const char*))("Actor_SkillSPCostRatio");
 float delta=METHOD(47585,float(*)(O*,O*,O*))(target,delta_key,0);
 float ratio=METHOD(47585,float(*)(O*,O*,O*))(target,ratio_key,0);
 return (amount+delta)*(1.0f+ratio);
}

static O* klass(U b,const char* space,const char* name) {
 O* domain=FN(domain_get,O*(*)(void))();U count=0;
 O** assemblies=FN(domain_get_assemblies,O**(*)(O*,U*))(domain,&count);
 if(!assemblies || count>1024)return 0;
 for(U i=0;i<count;i++) {
  O* image=FN(assembly_get_image,O*(*)(O*))(assemblies[i]);
  O* result=FN(class_from_name,O*(*)(O*,const char*,const char*))(image,space,name);
  if(result)return result;
 }
 return 0;
}
static O* invoke(U b,O* method,O* instance,void** args,O** ex) {
 if(!method || *ex)return 0;
 return FN(runtime_invoke,O*(*)(O*,O*,void**,O**))(method,instance,args,ex);
}
static O* named_method(U b,O* k,const char* name,int count) {
 return k?FN(class_get_method_from_name,O*(*)(O*,const char*,int))(k,name,count):0;
}
static int same_path(O* text,const char* ascii) {
 if(!text)return 0;
 U n=0;while(ascii[n])n++;
 if(*(U*)((char*)text+8)!=n)return 0;
 H* chars=(H*)((char*)text+12);
 for(U i=0;i<n;i++) {
  U c=chars[i];if(c>='A' && c<='Z')c+='a'-'A';
  if(c!=(unsigned char)ascii[i])return 0;
 }
 return 1;
}
/* Chain after the currently deployed original-first resource supplier. Only
 * six missing601 assets are eligible. Unity itself loads the real5.3 bundle;
 * Unload(false) leaves returned native objects alive without a native cache. */
EXPORT O* fuka_resource_supply(U b,O* path,O* original_method,O** ex) {
 const char* name=0;
 if(same_path(path,"entities/weapon/fist_f1/weapon_fist_f1_25_2"))name="entities/weapon/fist_f1/weapon_fist_f1_25_2";
 else if(same_path(path,"entities/weapon/fist_f1/weapon_fist_f1_25_3"))name="entities/weapon/fist_f1/weapon_fist_f1_25_3";
 else if(same_path(path,"spriteoutput/weaponicons/weapon_fist_f1_25_2"))name="spriteoutput/weaponicons/weapon_fist_f1_25_2";
 else if(same_path(path,"spriteoutput/weaponicons/weapon_fist_f1_25_3"))name="spriteoutput/weaponicons/weapon_fist_f1_25_3";
 else if(same_path(path,"effect/data/avatar/effectpattern_fuka_nl"))name="effect/data/avatar/effectpattern_fuka_nl";
 else if(same_path(path,"effect/data/weapon/effectpattern_fuka_weapon"))name="effect/data/weapon/effectpattern_fuka_weapon";
 if(!name || !original_method)return 0;
 O* k=klass(b,"UnityEngine","AssetBundle");
 O* location=FN(string_new,O*(*)(const char*))("/sdcard/bh3-server19-fuka601/fuka601-models.unity3d");
 void* file_args[1]={location};
 O* bundle=invoke(b,named_method(b,k,"LoadFromFile",1),0,file_args,ex);
 if(!bundle || *ex) {
  METHOD(18021,void(*)(O*,O*,O*))(0,FN(string_new,O*(*)(const char*))("BH3_FUKA601_BUNDLE_LOAD_FAILED"),0);
  return 0;
 }
 O* return_type=FN(method_get_return_type,O*(*)(O*))(original_method);
 O* type=FN(type_get_object,O*(*)(O*))(return_type);
 O* asset_name=FN(string_new,O*(*)(const char*))(name);
 void* asset_args[2]={asset_name,type};
 O* result=invoke(b,named_method(b,k,"LoadAsset",2),bundle,asset_args,ex);
 if(!*ex) {
  unsigned char all=0;void* unload_args[1]={&all};
  invoke(b,named_method(b,k,"Unload",1),bundle,unload_args,ex);
 }
 METHOD(18021,void(*)(O*,O*,O*))(0,FN(string_new,O*(*)(const char*))(result?"BH3_FUKA601_ASSET_LOADED":"BH3_FUKA601_ASSET_MISSING"),0);
 METHOD(18021,void(*)(O*,O*,O*))(0,path,0);
 return result;
}
