/* Original 1.9 ARM resource-input suppliers, compiled as freestanding A32 PIC.
 * No page/account/module initialization and no alternate player flow.
 * arm-resource-api.h is generated from the pinned ARM ELF/metadata mapping.
 * All potentially throwing file/JSON operations use runtime_invoke. Captured
 * exceptions leave via the assembly caller after its actual frame is restored.
 */
#include "arm-resource-api.h"
typedef unsigned int U;
typedef unsigned short H;
typedef unsigned char B;
typedef unsigned long long W;
typedef void O;
#define NIL ((O*)0)
#define FN(n,t) ((t)(b + ARMAPI_##n))
#define MF(i,t) ((t)(b + ARMM_##i))
#if defined(_MSC_VER)
#define LOCAL
#define EXPORTED __declspec(noinline)
#else
#define LOCAL __attribute__((visibility("hidden")))
#define EXPORTED __attribute__((visibility("hidden"),noinline))
#endif

static O* klass(U b, const char* space, const char* name) {
    O* domain=FN(domain_get,O*(*)(void))(); U count=0;
    O** all=FN(domain_get_assemblies,O**(*)(O*,U*))(domain,&count);
    if (!all || count>1024) return NIL;
    for(U i=0;i<count;i++) {
        O* image=FN(assembly_get_image,O*(*)(O*))(all[i]);
        O* result=FN(class_from_name,O*(*)(O*,const char*,const char*))(image,space,name);
        if(result) return result;
    }
    return NIL;
}
static O* field(U b,O* obj,const char* name) {
    if(!obj) return NIL;
    O* k=FN(object_get_class,O*(*)(O*))(obj);
    return FN(class_get_field_from_name,O*(*)(O*,const char*))(k,name);
}
static O* get_ref(U b,O* obj,const char* name) {
    O* f=field(b,obj,name); O* value=NIL;
    if(f) FN(field_get_value,void(*)(O*,O*,void*))(obj,f,&value);
    return value;
}
static int set_ref(U b,O* obj,const char* name,O* value) {
    O* f=field(b,obj,name); if(!f) return 0;
    /* Original1.9 Field.SetValue passes dereference=false to SetValueRaw.
     * CLASS/STRING/SZARRAY/GENERICINST-reference values are direct objects;
     * passing &value would write our stack address into the managed field.
     * Primitive/value-type setters below still receive addresses of values.
     */
    FN(field_set_value,void(*)(O*,O*,void*))(obj,f,value);
    O* readback=NIL;
    FN(field_get_value,void(*)(O*,O*,void*))(obj,f,&readback);
    if(readback!=value) {
        O* tag=FN(string_new,O*(*)(const char*))("BH3SERVER19_ARM_REFERENCE_WRITE_MISMATCH");
        MF(18021,void(*)(O*,O*,O*))(NIL,tag,NIL);
        MF(18021,void(*)(O*,O*,O*))(NIL,FN(string_new,O*(*)(const char*))(name),NIL);
        return 0;
    }
    return 1;
}
static int set_u32(U b,O* obj,const char* name,U value) {
    O* f=field(b,obj,name); if(!f) return 0;
    FN(field_set_value,void(*)(O*,O*,void*))(obj,f,&value); return 1;
}
static O* invoke(U b,O* method,O* instance,void** args,O** exception) {
    if(!method || *exception) return NIL;
    return FN(runtime_invoke,O*(*)(O*,O*,void**,O**))(method,instance,args,exception);
}
static O* method(U b,O* k,const char* name,U count) {
    if(!k) return NIL;
    return FN(class_get_method_from_name,O*(*)(O*,const char*,int))(k,name,(int)count);
}
static O* file_method(U b,const char* name,O* path,O** ex) {
    O* k=klass(b,"System.IO","File"); void* args[1]={path};
    if(name[0]=='R') MF(18021,void(*)(O*,O*,O*))(NIL,path,NIL);
    O* result=invoke(b,method(b,k,name,1),NIL,args,ex);
    if(*ex) {
        O* marker=FN(string_new,O*(*)(const char*))("BH3SERVER19_ARM_FILE_INVOKE_EXCEPTION");
        MF(18021,void(*)(O*,O*,O*))(NIL,marker,NIL);
    }
    return result;
}
static int exists(U b,O* path,O** ex) {
    O* boxed=file_method(b,"Exists",path,ex);
    if(!boxed || *ex) return 0;
    B* value=FN(object_unbox,B*(*)(O*))(boxed); return value && *value;
}
static O* string(U b,const char* text) { return FN(string_new,O*(*)(const char*))(text); }
static O* path_join(U b,const char* prefix,O* path,O** ex) {
    if(!path || *ex) return NIL;
    O* lower=MF(458,O*(*)(O*,O*))(path,NIL);
    return MF(475,O*(*)(O*,O*,O*,O*))(NIL,string(b,prefix),lower,NIL);
}
static U length(U b,O* array) { return array?FN(array_length,U(*)(O*))(array):0; }
static B* elements(O* array) { return ((B*)array)+ARM_ARRAY_DATA_OFFSET; }
static O* element_ref(U b,O* array,U i) {
    if(!array || i>=length(b,array)) return NIL;
    return ((O**)elements(array))[i];
}
static O* create_asset(U b,O* k) {
    if(!k) return NIL;
    O* t=FN(class_get_type,O*(*)(O*))(k);
    O* reflected=FN(type_get_object,O*(*)(O*))(t);
    return MF(16691,O*(*)(O*,O*,O*))(NIL,reflected,NIL);
}
static O* char_array(U b,H delimiter) {
    O* k=klass(b,"System","Char"); if(!k) return NIL;
    O* a=FN(array_new,O*(*)(O*,U))(k,1); if(a) *((H*)elements(a))=delimiter; return a;
}
static O* split(U b,O* text,H delimiter) {
    O* separator=char_array(b,delimiter); if(!text || !separator) return NIL;
    return MF(391,O*(*)(O*,O*,O*))(text,separator,NIL);
}
static void log(U b,const char* text) {
    MF(18021,void(*)(O*,O*,O*))(NIL,string(b,text),NIL);
}
static void log_exception_detail(U b,O* exception) {
    if(!exception) return;
    O* secondary=NIL;
    O* k=FN(object_get_class,O*(*)(O*))(exception);
    O* detail=invoke(b,method(b,k,"ToString",0),exception,(void**)0,&secondary);
    if(detail && !secondary) MF(18021,void(*)(O*,O*,O*))(NIL,detail,NIL);
}

EXPORTED O* arm_text_supply(U b,O* original_path,O** ex) {
    O* p=path_join(b,"/sdcard/bh3-server19-resources/",original_path,ex);
    if(!p || !exists(b,p,ex)) return NIL;
    return file_method(b,"ReadAllText",p,ex);
}
EXPORTED O* arm_stringmap_supply(U b,O** ex) {
    O* p=string(b,"/sdcard/bh3-server19-baked/_baked/stringmap.txt");
    if(!exists(b,p,ex)) return NIL;
    O* text=file_method(b,"ReadAllText",p,ex); if(*ex) return NIL;
    O* values=split(b,text,0x1f); if(!values) return NIL;
    log(b,"BH3SERVER19_ARM_STRINGMAP_SPLIT_OK");
    O* asset=create_asset(b,klass(b,"MoleMole.Bake","PackedStringMap"));
    if(!asset || !set_ref(b,asset,"strings",values) || !set_u32(b,asset,"packedHash",ARM_STRINGMAP_HASH)) return NIL;
    log(b,"BH3SERVER19_ARM_STRINGMAP_REFERENCE_READBACK_OK");
    return asset;
}
/* Prevent LLVM forming an absolute pointer lookup table in RX-only storage. */
#if defined(_MSC_VER)
static const char* meta_field(U i) {
#else
static __attribute__((optnone,noinline)) const char* meta_field(U i) {
#endif
    if(i==0) return "effectPatternPathes";
    if(i==1) return "stageEntryPathes";
    if(i==2) return "auxEntryPathes";
    if(i==3) return "dynamicObjectRegistryPathes";
    if(i==4) return "renderEntryPathes";
    if(i==5) return "weatherEntryPathes";
    if(i==6) return "animatorEventPatternPathes";
    if(i==7) return "touchPatternPathes";
    if(i==8) return "navMeshScenes";
    if(i==9) return "graphicsSettingRegistryPathes";
    if(i==10) return "cameraCurvePatternPathes";
    if(i==11) return "groupAIGridPathes";
    return "effectPatternNamesRegistryPathes";
}
EXPORTED O* arm_metaconfig_supply(U b,O** ex) {
    O* p=string(b,"/sdcard/bh3-server19-baked/metaconfig.txt");
    if(!exists(b,p,ex)) return NIL;
    O* text=file_method(b,"ReadAllText",p,ex); if(*ex) return NIL;
    O* groups=split(b,text,0x1e); if(length(b,groups)!=13) return NIL;
    O* asset=create_asset(b,klass(b,"MoleMole","ConfigMetaConfig")); if(!asset) return NIL;
    for(U i=0;i<13;i++) {
        O* values=split(b,element_ref(b,groups,i),0x1f);
        if(!values || !set_ref(b,asset,meta_field(i),values)) return NIL;
    }
    log(b,"BH3SERVER19_ARM_METACONFIG_REFERENCE_READBACK_OK");
    /* atmosphere/cleared-atmosphere/gal-touch/volatile paths remain ctor-owned. */
    return asset;
}
static int list_backing(U b,O* asset,const char* fieldname,O* array,U count,O** ex) {
    O* f=field(b,asset,fieldname); if(!f) return 0;
    O* list=get_ref(b,asset,fieldname);
    if(!list) {
        O* t=FN(field_get_type,O*(*)(O*))(f);
        O* k=FN(class_from_type,O*(*)(O*))(t);
        if(!k) return 0;
        list=FN(object_new,O*(*)(O*))(k); if(!list) return 0;
        invoke(b,method(b,k,".ctor",0),list,(void**)0,ex);
        if(*ex) return 0;
    }
    return set_ref(b,list,"_items",array) && set_u32(b,list,"_size",count) && set_ref(b,asset,fieldname,list);
}
static int array_from_bytes(U b,O* raw,U* cursor,U stride,const char* space,const char* type,O** result,U* count) {
    U total=length(b,raw); if(*cursor>total || total-*cursor<4) return 0;
    B* data=elements(raw); U n=*((U*)(data+*cursor)); *cursor+=4;
    W wide=(W)n*stride;
    if(n>0x7fffffffU || wide>0x7fffffffU || wide>(U)(total-*cursor)) return 0;
    O* k=klass(b,space,type); if(!k) return 0;
    U alignment=0;
    U actual=FN(class_value_size,U(*)(O*,U*))(k,&alignment);
    if(actual!=stride) return 0;
    O* a=FN(array_new,O*(*)(O*,U))(k,n); if(!a) return 0;
    B* dst=elements(a); U bytes=n*stride;
    for(U i=0;i<bytes;i++) dst[i]=data[*cursor+i];
    *cursor+=bytes; *result=a; *count=n; return 1;
}
EXPORTED O* arm_baked_supply(U b,O* original_path,O** ex) {
    O* p=path_join(b,"/sdcard/bh3-server19-baked/",original_path,ex);
    if(!p || !exists(b,p,ex)) return NIL;
    O* raw=file_method(b,"ReadAllBytes",p,ex); if(*ex || length(b,raw)<8) return NIL;
    U* header=(U*)elements(raw); U indexed=header[0],hash=header[1]; if(indexed>1) return NIL;
    O* asset=create_asset(b,klass(b,"MoleMole.Bake",indexed?"PackedIndexConfigContainer":"PackedConfigContainer"));
    if(!asset) return NIL;
    U cursor=8,count=0; O* a=NIL;
    if(indexed) {
        if(!array_from_bytes(b,raw,&cursor,4,"System","Int32",&a,&count) || !list_backing(b,asset,"offsets",a,count,ex)) return NIL;
    } else {
        if(!array_from_bytes(b,raw,&cursor,8,"MoleMole.Bake","PackedEntry",&a,&count) || !list_backing(b,asset,"indices",a,count,ex)) return NIL;
        if(!array_from_bytes(b,raw,&cursor,12,"MoleMole.Bake","PackedOverrideEntry",&a,&count) || !list_backing(b,asset,"overrideIndices",a,count,ex)) return NIL;
    }
    if(!array_from_bytes(b,raw,&cursor,1,"System","Byte",&a,&count) || cursor!=length(b,raw)) return NIL;
    if(!set_ref(b,asset,"packedBytes",a) || !set_u32(b,asset,"packedHash",hash)) return NIL;
    return *ex?NIL:asset;
}
static int succeeded(U b,O* boxed_result) {
    B success=0; O* f=field(b,boxed_result,"_success"); if(!f) return 0;
    FN(field_get_value,void(*)(O*,O*,void*))(boxed_result,f,&success); return success!=0;
}
static int restore_chars(U b,O* path,O* list,O** ex) {
    O* chars=MF(475,O*(*)(O*,O*,O*,O*))(NIL,path,string(b,".chars"),NIL);
    if(!exists(b,chars,ex)) return *ex?0:1;
    O* raw=file_method(b,"ReadAllBytes",chars,ex); if(*ex || !raw) return 0;
    O* items=get_ref(b,list,"_items"); O* sizefield=field(b,list,"_size"); U count=0;
    if(!items || !sizefield) return 0;
    FN(field_get_value,void(*)(O*,O*,void*))(list,sizefield,&count);
    if(count>length(b,items) || count>0x7fffffffU/6 || length(b,raw)!=count*6) return 0;
    H* values=(H*)elements(raw);
    for(U k=0;k<3;k++) for(U i=0;i<count;i++) {
        O* row=element_ref(b,items,i); O* f=field(b,row,k==0?"paramLogic_1":k==1?"paramLogic_2":"paramLogic_3"); if(!f) return 0;
        H value=values[k*count+i]; FN(field_set_value,void(*)(O*,O*,void*))(row,f,&value);
    }
    return 1;
}
EXPORTED O* arm_typed_supply(U b,O* original_path,O* original_method,O** ex) {
    if(!original_method) return NIL;
    O* returned=FN(method_get_return_type,O*(*)(O*))(original_method);
    O* assetclass=FN(class_from_type,O*(*)(O*))(returned);
    if(!assetclass) return NIL;
    O* itemfield=FN(class_get_field_from_name,O*(*)(O*,const char*))(assetclass,"itemList");
    if(!itemfield) return NIL;
    O* p=path_join(b,"/sdcard/bh3-server19-metadata/",original_path,ex);
    if(!p || !exists(b,p,ex)) return NIL;
    O* text=file_method(b,"ReadAllText",p,ex); if(*ex) return NIL;
    MF(87740,void(*)(O*,O*))(NIL,NIL);
    O* util=klass(b,"MoleMole","ConfigUtil"); O* serializer=NIL; if(!util) return NIL;
    O* sf=FN(class_get_field_from_name,O*(*)(O*,const char*))(util,"_jsonSerializer"); if(!sf) return NIL;
    FN(field_static_get_value,void(*)(O*,void*))(sf,&serializer); if(!serializer) return NIL;
    /* Each supplied table owns its serializer cycle/reference state. Native
     * ConfigUtil still keeps its original shared serializer for native calls.
     * Retain its configured processors, but never share converter caches or
     * mutable Enter/Exit counters with interleaved config loads. */
    O* shared=serializer;
    O* skclass=FN(object_get_class,O*(*)(O*))(shared);
    serializer=FN(object_new,O*(*)(O*))(skclass);
    if(!serializer) return NIL;
    invoke(b,method(b,skclass,".ctor",0),serializer,NIL,ex);
    if(*ex) return NIL;
    O* processors=get_ref(b,shared,"_processors");
    O* processor_items=get_ref(b,processors,"_items"); U processor_count=0;
    O* processor_size=field(b,processors,"_size");
    if(!processor_items || !processor_size) return NIL;
    FN(field_get_value,void(*)(O*,O*,void*))(processors,processor_size,&processor_count);
    if(processor_count>length(b,processor_items)) return NIL;
    for(U i=0;i<processor_count;i++) {
        O* processor=element_ref(b,processor_items,i);
        void* args[1]={processor};
        invoke(b,method(b,skclass,"AddProcessor",1),serializer,args,ex);
        if(*ex) return NIL;
    }
    O* parser=klass(b,"FullSerializer","fsJsonParser"); O* parsed=NIL;
    void* parse_args[2]={text,&parsed};
    O* status=invoke(b,method(b,parser,"Parse",2),NIL,parse_args,ex);
    if(*ex || !parsed || !succeeded(b,status)) { log(b,"BH3SERVER19_ARM_TABLE_PARSE_FAILED"); return NIL; }
    O* fieldtype=FN(field_get_type,O*(*)(O*))(itemfield);
    O* reflected=FN(type_get_object,O*(*)(O*))(fieldtype); O* list=NIL;
    void* deserialize_args[3]={parsed,reflected,&list};
    O* sk=FN(object_get_class,O*(*)(O*))(serializer);
    status=invoke(b,method(b,sk,"TryDeserialize",3),serializer,deserialize_args,ex);
    if(*ex || !list || !succeeded(b,status)) {
        log(b,"BH3SERVER19_ARM_TABLE_DESERIALIZE_FAILED");
        log_exception_detail(b,*ex);
        return NIL;
    }
    if(!restore_chars(b,p,list,ex)) return NIL;
    O* asset=create_asset(b,assetclass);
    if(!asset || !set_ref(b,asset,"itemList",list)) return NIL;
    return asset;
}
static int same_text(const char* a,const char* z) {
    if(!a || !z) return 0;
    while(*a && *a==*z) { a++;z++; }
    return *a==*z;
}
EXPORTED O* arm_generic_supply(U b,O* original_path,O* original_method,O** ex) {
    if(!original_method) return NIL;
    O* t=FN(method_get_return_type,O*(*)(O*))(original_method);
    O* k=FN(class_from_type,O*(*)(O*))(t); if(!k) return NIL;
    if(FN(class_get_field_from_name,O*(*)(O*,const char*))(k,"itemList"))
        return arm_typed_supply(b,original_path,original_method,ex);
    const char* space=FN(class_get_namespace,const char*(*)(O*))(k);
    const char* name=FN(class_get_name,const char*(*)(O*))(k);
    if(!same_text(space,"MoleMole.Bake") ||
       (!same_text(name,"PackedConfigContainer") && !same_text(name,"PackedIndexConfigContainer"))) return NIL;
    O* asset=arm_baked_supply(b,original_path,ex);
    if(asset && FN(object_get_class,O*(*)(O*))(asset)!=k) return NIL;
    return asset;
}
EXPORTED O* arm_async_json_supply(U b,O* coroutine,U selector,O** ex) {
    O* path=NIL;
    if(selector==0) {
        O* paths=get_ref(b,coroutine,"<effectPatternNamesRegistryPathes>__1");
        O* f=field(b,coroutine,"<ix>__8"); U index=0;
        if(!f) return NIL; FN(field_get_value,void(*)(O*,O*,void*))(coroutine,f,&index);
        path=element_ref(b,paths,index);
    } else if(selector==1) {
        O* manager=klass(b,"MoleMole","GlobalDataManager"); O* cfg=NIL; if(!manager) return NIL;
        O* f=FN(class_get_field_from_name,O*(*)(O*,const char*))(manager,"metaConfig"); if(!f) return NIL;
        FN(field_static_get_value,void(*)(O*,void*))(f,&cfg);
        path=get_ref(b,cfg,"graphicsVolatileSettingRegistryPath");
    } else if(selector==2) path=get_ref(b,coroutine,"<configFilePath>__6");
    else if(selector==3) path=get_ref(b,coroutine,"<gridFilePath>__7");
    return arm_text_supply(b,path,ex);
}
