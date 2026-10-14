#pragma once
namespace binding::objects {
inline constexpr const char *factory_source = R"JS(
(() => {
  const O=Object, R=Reflect, P=Proxy, define=O.defineProperty;
  const global=globalThis;
  const identities=new WeakMap();
  function proxy(native, callable, token) {
    const target=callable ? (...args)=>native('call',args) : O.create(null);
    const value=new P(target, {
      get(t,k) {
        native('guard');
        if(k===Symbol.toStringTag) return 'PythonProxy';
        if(typeof k!=='string') return undefined;
        if(native('has',k)) return native('get',k);
        if(callable && ['call','apply','bind','name','length'].includes(k)) return R.get(t,k);
        return undefined;
      },
      set(t,k,v) {native('set',k,v); return true;},
      has(t,k) {native('guard');return typeof k==='string' && native('has',k);},
      ownKeys() {return native('keys');},
      getOwnPropertyDescriptor(t,k) {
        native('guard');
        if(typeof k==='string' && native('has',k)) return {configurable:true,enumerable:true};
        return R.getOwnPropertyDescriptor(t,k);
      },
      deleteProperty() {native('guard');throw new TypeError('Use Python.delitem for element deletion');},
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
  return {proxy,install,bind,remove,namespace,register,unregister,lookup:value=>identities.get(value)};
})()
)JS";
}
