#pragma once
namespace binding::objects {
inline constexpr const char *factory_source = R"JS(
(() => {
  const O=Object, R=Reflect, P=Proxy, define=O.defineProperty;
  const global=globalThis;
  const identities=new WeakMap();
  const jsIdentities=new WeakMap();
  let sequence=0;
  const splice=Array.prototype.splice;
  // Private read codes shared with proxy.hpp.
  const itemGet=1, itemHas=2, itemLength=3;
  const index=k=>typeof k==='string' && /^(0|[1-9][0-9]*)$/.test(k) && +k<4294967295;
  function identify(value) {
    if(!jsIdentities.has(value)) jsIdentities.set(value,++sequence);
    return jsIdentities.get(value);
  }
  function container(value,op,...args) {
    if(op==='length') return value.length;
    if(op==='get') return R.get(value,args[0]);
    if(op==='set') {
      if(!R.set(value,args[0],args[1])) throw new TypeError('JavaScript property is read-only');
    } else if(op==='delete') {
      if(!R.deleteProperty(value,args[0])) throw new TypeError('JavaScript property cannot be deleted');
    } else if(op==='splice') {
      R.apply(splice,value,args);
    } else throw new TypeError('Unknown JavaScript container operation: '+op);
  }
  function proxy(native, callable, token, kind) {
    const array=kind==='list', mapping=kind==='dict', data=array||mapping;
    const target=array ? [] : callable ? (...args)=>native('call',args) : O.create(null);
    const has=k=>typeof k==='string' && (!array||index(k)) && native(itemHas,array ? +k : k);
    function syncLength() {
      const length=native(itemLength);
      if(length>4294967295) throw new RangeError('Python list exceeds JavaScript Array length');
      target.length=length;
      return length;
    }
    const value=new P(target, {
      get(t,k,r) {
        if(array) {
          if(k==='length') return syncLength();
          if(index(k)) return native(itemGet,+k);
          native('guard');
          return R.get(t,k,r);
        }
        if(mapping && typeof k==='string') return native(itemGet,k);
        native('guard');
        if(mapping) return undefined;
        if(k===Symbol.toStringTag) return 'PythonProxy';
        if(typeof k!=='string') return undefined;
        if(native('has',k)) return native('get',k);
        if(callable && ['call','apply','bind','name','length'].includes(k)) return R.get(t,k);
        return undefined;
      },
      set(t,k,v) {
        native('guard');
        if(array && k==='length') {
          const n=+v;
          if(!Number.isInteger(n)||n<0||n>4294967295) throw new RangeError('Invalid array length');
          native('item_resize',n); syncLength(); return true;
        }
        if(data) {
          if(typeof k!=='string'||(array&&!index(k))) throw new TypeError('Unsupported Python container property');
          native('item_set',k,v); return true;
        }
        native('set',k,v); return true;
      },
      has(t,k) {
        if(data && typeof k==='string' && (!array||index(k))) return native(itemHas,array ? +k : k) || (array && R.has(t,k));
        native('guard');
        if(array) return k==='length'||has(k)||R.has(t,k);
        return data ? has(k) : typeof k==='string' && native('has',k);
      },
      ownKeys() {
        if(array) syncLength();
        return data ? array ? [...native('item_keys'),'length'] : native('item_keys') : native('keys');
      },
      getOwnPropertyDescriptor(t,k) {
        if(array && k==='length') {syncLength();return R.getOwnPropertyDescriptor(t,k);}
        if(data && typeof k==='string' && (!array||index(k)))
          return has(k) ? {configurable:true,enumerable:true,writable:true,value:native(itemGet,array ? +k : k)} : undefined;
        native('guard');
        if(data) return undefined;
        if(typeof k==='string' && native('has',k)) return {configurable:true,enumerable:true};
        return R.getOwnPropertyDescriptor(t,k);
      },
      deleteProperty(t,k) {
        native('guard');
        if(data && typeof k==='string' && (!array||index(k))) {native('item_delete',k);return true;}
        throw new TypeError('Unsupported Python proxy deletion');
      },
      defineProperty() {native('guard');throw new TypeError('Python proxy descriptors cannot be changed');},
      getPrototypeOf(t) {native('guard');return R.getPrototypeOf(t);},
      isExtensible(t) {native('guard');return R.isExtensible(t);},
      setPrototypeOf() {native('guard');throw new TypeError('Python proxy prototypes cannot be changed');},
      preventExtensions() {native('guard');throw new TypeError('Python proxies cannot be frozen');}
    });
    identities.set(value,token);
    return value;
  }
  function install(native) {
    if(O.getOwnPropertyDescriptor(global,'Python')) throw new TypeError('Python is a reserved bridge name');
    const helpers=O.create(null);
    for(const name of ['getattr','getitem','setitem','delitem','len','contains','slice','call','to_value'])
      helpers[name]=(...args)=>native(name,args);
    helpers.iter=(obj)=>{
      const next=native('iter',[obj]);
      return {next:()=>next(),return:()=>next(true),[Symbol.iterator](){return this;}};
    };
    define(global,'Python',{value:O.freeze(helpers),writable:false,configurable:false});
  }
  function bind(name,value) {
    if(name==='Python') throw new TypeError('Python is a reserved bridge name');
    define(global,name,{value,writable:true,enumerable:true,configurable:true});
  }
  function remove(name,value) {
    const d=O.getOwnPropertyDescriptor(global,name);
    if(d && d.value===value && d.configurable) delete global[name];
  }
  function namespace(name) {
    if(O.getOwnPropertyDescriptor(global,name)) throw new TypeError('API namespace already exists: '+name);
    const value=O.create(null);
    define(global,name,{value,writable:false,enumerable:true,configurable:true});
    return value;
  }
  function register(target,name,value) {
    define(target,name,{value,writable:false,enumerable:true,configurable:true});
  }
  function unregister(target,name,value) {
    const d=O.getOwnPropertyDescriptor(target,name);
    if(d && d.value===value && d.configurable) delete target[name];
  }
  return {proxy,install,bind,remove,namespace,register,unregister,identify,container,array:Array.isArray,lookup:value=>identities.get(value)};
})()
)JS";
}
