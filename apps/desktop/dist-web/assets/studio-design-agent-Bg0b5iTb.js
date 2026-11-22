const __vite__mapDeps=(i,m=__vite__mapDeps,d=(m.f||(m.f=["assets/esm-Ciwn2iui.js","assets/rolldown-runtime-BYbx6iT9.js","assets/objectWithoutPropertiesLoose-CKUp3axZ.js"])))=>i.map(i=>d[i]);
import{a as e,r as t,t as n}from"./rolldown-runtime-BYbx6iT9.js";var r={BASE_URL:`/`,DEV:!1,MODE:`production`,PROD:!0,SSR:!1};function i(e,t){return e===void 0||e===``?t:e===`1`||e===`true`}function a(){return typeof window>`u`?{}:window}var o=`https://tchuekam-agent-production.up.railway.app`;function s(){let e=String(r.VITE_HERMES_API_URL??``).replace(/\/+$/,``);if(e)return e;if(!a().__HERMES_SESSION_TOKEN__&&!a().__HERMES_AUTH_REQUIRED__&&typeof window<`u`){let e=window.location.hostname,t=typeof a().__HERMES_AUTH_REQUIRED__==`boolean`;if(e.endsWith(`.vercel.app`)||e.endsWith(`.netlify.app`)||!t&&(e===`tchuekam.com`||e.endsWith(`.tchuekam.com`)))return o}return``}var c={apiUrl:s(),get token(){return String(a().__HERMES_SESSION_TOKEN__??r.VITE_HERMES_TOKEN??``)},get basePath(){return String(a().__HERMES_BASE_PATH__??``).replace(/\/+$/,``)},get authRequired(){return a().__HERMES_AUTH_REQUIRED__===!0},version:String(r.VITE_HERMES_APP_VERSION??`web`),demo:i(r.VITE_HERMES_DEMO,!0)},l=c.demo,u=`modulepreload`,d=function(e){return`/`+e},f={},p=function(e,t,n){let r=Promise.resolve();if(t&&t.length>0){let e=document.getElementsByTagName(`link`),i=document.querySelector(`meta[property=csp-nonce]`),a=i?.nonce||i?.getAttribute(`nonce`);function o(e){return Promise.all(e.map(e=>Promise.resolve(e).then(e=>({status:`fulfilled`,value:e}),e=>({status:`rejected`,reason:e}))))}r=o(t.map(t=>{if(t=d(t,n),t in f)return;f[t]=!0;let r=t.endsWith(`.css`),i=r?`[rel="stylesheet"]`:``;if(n)for(let n=e.length-1;n>=0;n--){let i=e[n];if(i.href===t&&(!r||i.rel===`stylesheet`))return}else if(document.querySelector(`link[href="${t}"]${i}`))return;let o=document.createElement(`link`);if(o.rel=r?`stylesheet`:u,r||(o.as=`script`),o.crossOrigin=``,o.href=t,a&&o.setAttribute(`nonce`,a),document.head.appendChild(o),r)return new Promise((e,n)=>{o.addEventListener(`load`,e),o.addEventListener(`error`,()=>n(Error(`Unable to preload CSS for ${t}`)))})}))}function i(e){let t=new Event(`vite:preloadError`,{cancelable:!0});if(t.payload=e,window.dispatchEvent(t),!t.defaultPrevented)throw e}return r.then(t=>{for(let e of t||[])e.status===`rejected`&&i(e.reason);return e().catch(i)})},m=n((e=>{var t=Symbol.for(`react.transitional.element`),n=Symbol.for(`react.portal`),r=Symbol.for(`react.fragment`),i=Symbol.for(`react.strict_mode`),a=Symbol.for(`react.profiler`),o=Symbol.for(`react.consumer`),s=Symbol.for(`react.context`),c=Symbol.for(`react.forward_ref`),l=Symbol.for(`react.suspense`),u=Symbol.for(`react.memo`),d=Symbol.for(`react.lazy`),f=Symbol.for(`react.activity`),p=Symbol.iterator;function m(e){return typeof e!=`object`||!e?null:(e=p&&e[p]||e[`@@iterator`],typeof e==`function`?e:null)}var h={isMounted:function(){return!1},enqueueForceUpdate:function(){},enqueueReplaceState:function(){},enqueueSetState:function(){}},g=Object.assign,_={};function v(e,t,n){this.props=e,this.context=t,this.refs=_,this.updater=n||h}v.prototype.isReactComponent={},v.prototype.setState=function(e,t){if(typeof e!=`object`&&typeof e!=`function`&&e!=null)throw Error(`takes an object of state variables to update or a function which returns an object of state variables.`);this.updater.enqueueSetState(this,e,t,`setState`)},v.prototype.forceUpdate=function(e){this.updater.enqueueForceUpdate(this,e,`forceUpdate`)};function y(){}y.prototype=v.prototype;function b(e,t,n){this.props=e,this.context=t,this.refs=_,this.updater=n||h}var x=b.prototype=new y;x.constructor=b,g(x,v.prototype),x.isPureReactComponent=!0;var S=Array.isArray;function C(){}var w={H:null,A:null,T:null,S:null},T=Object.prototype.hasOwnProperty;function E(e,n,r){var i=r.ref;return{$$typeof:t,type:e,key:n,ref:i===void 0?null:i,props:r}}function ee(e,t){return E(e.type,t,e.props)}function D(e){return typeof e==`object`&&!!e&&e.$$typeof===t}function te(e){var t={"=":`=0`,":":`=2`};return`$`+e.replace(/[=:]/g,function(e){return t[e]})}var ne=/\/+/g;function O(e,t){return typeof e==`object`&&e&&e.key!=null?te(``+e.key):t.toString(36)}function re(e){switch(e.status){case`fulfilled`:return e.value;case`rejected`:throw e.reason;default:switch(typeof e.status==`string`?e.then(C,C):(e.status=`pending`,e.then(function(t){e.status===`pending`&&(e.status=`fulfilled`,e.value=t)},function(t){e.status===`pending`&&(e.status=`rejected`,e.reason=t)})),e.status){case`fulfilled`:return e.value;case`rejected`:throw e.reason}}throw e}function k(e,r,i,a,o){var s=typeof e;(s===`undefined`||s===`boolean`)&&(e=null);var c=!1;if(e===null)c=!0;else switch(s){case`bigint`:case`string`:case`number`:c=!0;break;case`object`:switch(e.$$typeof){case t:case n:c=!0;break;case d:return c=e._init,k(c(e._payload),r,i,a,o)}}if(c)return o=o(e),c=a===``?`.`+O(e,0):a,S(o)?(i=``,c!=null&&(i=c.replace(ne,`$&/`)+`/`),k(o,r,i,``,function(e){return e})):o!=null&&(D(o)&&(o=ee(o,i+(o.key==null||e&&e.key===o.key?``:(``+o.key).replace(ne,`$&/`)+`/`)+c)),r.push(o)),1;c=0;var l=a===``?`.`:a+`:`;if(S(e))for(var u=0;u<e.length;u++)a=e[u],s=l+O(a,u),c+=k(a,r,i,s,o);else if(u=m(e),typeof u==`function`)for(e=u.call(e),u=0;!(a=e.next()).done;)a=a.value,s=l+O(a,u++),c+=k(a,r,i,s,o);else if(s===`object`){if(typeof e.then==`function`)return k(re(e),r,i,a,o);throw r=String(e),Error(`Objects are not valid as a React child (found: `+(r===`[object Object]`?`object with keys {`+Object.keys(e).join(`, `)+`}`:r)+`). If you meant to render a collection of children, use an array instead.`)}return c}function A(e,t,n){if(e==null)return e;var r=[],i=0;return k(e,r,``,``,function(e){return t.call(n,e,i++)}),r}function j(e){if(e._status===-1){var t=e._result;t=t(),t.then(function(t){(e._status===0||e._status===-1)&&(e._status=1,e._result=t)},function(t){(e._status===0||e._status===-1)&&(e._status=2,e._result=t)}),e._status===-1&&(e._status=0,e._result=t)}if(e._status===1)return e._result.default;throw e._result}var ie=typeof reportError==`function`?reportError:function(e){if(typeof window==`object`&&typeof window.ErrorEvent==`function`){var t=new window.ErrorEvent(`error`,{bubbles:!0,cancelable:!0,message:typeof e==`object`&&e&&typeof e.message==`string`?String(e.message):String(e),error:e});if(!window.dispatchEvent(t))return}else if(typeof process==`object`&&typeof process.emit==`function`){process.emit(`uncaughtException`,e);return}console.error(e)},ae={map:A,forEach:function(e,t,n){A(e,function(){t.apply(this,arguments)},n)},count:function(e){var t=0;return A(e,function(){t++}),t},toArray:function(e){return A(e,function(e){return e})||[]},only:function(e){if(!D(e))throw Error(`React.Children.only expected to receive a single React element child.`);return e}};e.Activity=f,e.Children=ae,e.Component=v,e.Fragment=r,e.Profiler=a,e.PureComponent=b,e.StrictMode=i,e.Suspense=l,e.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE=w,e.__COMPILER_RUNTIME={__proto__:null,c:function(e){return w.H.useMemoCache(e)}},e.cache=function(e){return function(){return e.apply(null,arguments)}},e.cacheSignal=function(){return null},e.cloneElement=function(e,t,n){if(e==null)throw Error(`The argument must be a React element, but you passed `+e+`.`);var r=g({},e.props),i=e.key;if(t!=null)for(a in t.key!==void 0&&(i=``+t.key),t)!T.call(t,a)||a===`key`||a===`__self`||a===`__source`||a===`ref`&&t.ref===void 0||(r[a]=t[a]);var a=arguments.length-2;if(a===1)r.children=n;else if(1<a){for(var o=Array(a),s=0;s<a;s++)o[s]=arguments[s+2];r.children=o}return E(e.type,i,r)},e.createContext=function(e){return e={$$typeof:s,_currentValue:e,_currentValue2:e,_threadCount:0,Provider:null,Consumer:null},e.Provider=e,e.Consumer={$$typeof:o,_context:e},e},e.createElement=function(e,t,n){var r,i={},a=null;if(t!=null)for(r in t.key!==void 0&&(a=``+t.key),t)T.call(t,r)&&r!==`key`&&r!==`__self`&&r!==`__source`&&(i[r]=t[r]);var o=arguments.length-2;if(o===1)i.children=n;else if(1<o){for(var s=Array(o),c=0;c<o;c++)s[c]=arguments[c+2];i.children=s}if(e&&e.defaultProps)for(r in o=e.defaultProps,o)i[r]===void 0&&(i[r]=o[r]);return E(e,a,i)},e.createRef=function(){return{current:null}},e.forwardRef=function(e){return{$$typeof:c,render:e}},e.isValidElement=D,e.lazy=function(e){return{$$typeof:d,_payload:{_status:-1,_result:e},_init:j}},e.memo=function(e,t){return{$$typeof:u,type:e,compare:t===void 0?null:t}},e.startTransition=function(e){var t=w.T,n={};w.T=n;try{var r=e(),i=w.S;i!==null&&i(n,r),typeof r==`object`&&r&&typeof r.then==`function`&&r.then(C,ie)}catch(e){ie(e)}finally{t!==null&&n.types!==null&&(t.types=n.types),w.T=t}},e.unstable_useCacheRefresh=function(){return w.H.useCacheRefresh()},e.use=function(e){return w.H.use(e)},e.useActionState=function(e,t,n){return w.H.useActionState(e,t,n)},e.useCallback=function(e,t){return w.H.useCallback(e,t)},e.useContext=function(e){return w.H.useContext(e)},e.useDebugValue=function(){},e.useDeferredValue=function(e,t){return w.H.useDeferredValue(e,t)},e.useEffect=function(e,t){return w.H.useEffect(e,t)},e.useEffectEvent=function(e){return w.H.useEffectEvent(e)},e.useId=function(){return w.H.useId()},e.useImperativeHandle=function(e,t,n){return w.H.useImperativeHandle(e,t,n)},e.useInsertionEffect=function(e,t){return w.H.useInsertionEffect(e,t)},e.useLayoutEffect=function(e,t){return w.H.useLayoutEffect(e,t)},e.useMemo=function(e,t){return w.H.useMemo(e,t)},e.useOptimistic=function(e,t){return w.H.useOptimistic(e,t)},e.useReducer=function(e,t,n){return w.H.useReducer(e,t,n)},e.useRef=function(e){return w.H.useRef(e)},e.useState=function(e){return w.H.useState(e)},e.useSyncExternalStore=function(e,t,n){return w.H.useSyncExternalStore(e,t,n)},e.useTransition=function(){return w.H.useTransition()},e.version=`19.2.5`})),h=n(((e,t)=>{t.exports=m()})),g=n((e=>{var t=Symbol.for(`react.transitional.element`),n=Symbol.for(`react.fragment`);function r(e,n,r){var i=null;if(r!==void 0&&(i=``+r),n.key!==void 0&&(i=``+n.key),`key`in n)for(var a in r={},n)a!==`key`&&(r[a]=n[a]);else r=n;return n=r.ref,{$$typeof:t,type:e,key:i,ref:n===void 0?null:n,props:r}}e.Fragment=n,e.jsx=r,e.jsxs=r})),_=n(((e,t)=>{t.exports=g()})),v=_(),y=e(h(),1),b=`/image-studio`;function x(){if(typeof window>`u`)return{path:b,query:``};let[e,t=``]=(window.location.hash.replace(/^#/,``)||`/image-studio`).split(`?`);return{path:e||`/image-studio`,query:t}}function S(e){let t=new URLSearchParams(e),n=new URLSearchParams(x().query);for(let e of[...n.keys()])e!==`tab`&&n.delete(e);for(let[e,r]of t)n.set(e,r);return n}function C(e){let{path:t}=x(),n=t.startsWith(`/image-studio`)?t:b,r=e.toString();return r?`${n}?${r}`:n}function w(e){if(e.startsWith(`?`))return C(S(e.slice(1)));let[t,n=``]=e.split(`?`),r=e.split(`/studio/`)[1]?.split(/[?#]/)[0]||new URLSearchParams(n).get(`tab`);if(r){let e=S(n);return e.set(`tab`,r),C(e)}if(t&&t!==`/`){let e=S(``);return e.delete(`session`),C(e)}return C(S(n))}function T(e){return e.startsWith(`http://`)||e.startsWith(`https://`)||e.startsWith(`mailto:`)}function E(e){typeof window>`u`||(window.hermesDesktop?.openExternal?window.hermesDesktop.openExternal(e):window.open(e,`_blank`,`noopener,noreferrer`))}function ee(e,t){if(typeof window>`u`||!e)return;if(T(e)){E(e);return}let n=`#${w(e)}`;window.location.hash!==n&&(t===`replace`?window.history.replaceState(null,``,n):window.history.pushState(null,``,n),window.dispatchEvent(new Event(`hashchange`)),window.dispatchEvent(new Event(`popstate`)))}function D(){let[e,t]=y.useState(()=>typeof window>`u`?``:window.location.hash);return y.useEffect(()=>{let e=()=>t(window.location.hash);return window.addEventListener(`popstate`,e),window.addEventListener(`hashchange`,e),()=>{window.removeEventListener(`popstate`,e),window.removeEventListener(`hashchange`,e)}},[]),e}function te(){return y.useMemo(()=>({back:()=>{typeof window<`u`&&window.history.back()},forward:()=>{typeof window<`u`&&window.history.forward()},prefetch:()=>{},push:e=>ee(e,`push`),refresh:()=>{},replace:e=>ee(e,`replace`)}),[])}function ne(){return{}}function O(){D();let e=x().query;return y.useMemo(()=>new URLSearchParams(e),[e])}function re(e,t={}){let n=y.lazy(async()=>{let t=await e();return t&&typeof t==`object`&&t.default?t:typeof t==`function`||t&&typeof t==`object`?{default:t}:{default:()=>null}}),r=t.loading||(()=>null);return function(e){return(0,v.jsx)(y.Suspense,{fallback:(0,v.jsx)(r,{}),children:(0,v.jsx)(n,{...e})})}}var k={data:``},A=e=>{if(typeof window==`object`){let t=(e?e.querySelector(`#_goober`):window._goober)||Object.assign(document.createElement(`style`),{innerHTML:` `,id:`_goober`});return t.nonce=window.__nonce__,t.parentNode||(e||document.head).appendChild(t),t.firstChild}return e||k},j=/(?:([\u0080-\uFFFF\w-%@]+) *:? *([^{;]+?);|([^;}{]*?) *{)|(}\s*)/g,ie=/\/\*[^]*?\*\/|  +/g,ae=/\n+/g,oe=(e,t)=>{let n=``,r=``,i=``;for(let a in e){let o=e[a];a[0]==`@`?a[1]==`i`?n=a+` `+o+`;`:r+=a[1]==`f`?oe(o,a):a+`{`+oe(o,a[1]==`k`?``:t)+`}`:typeof o==`object`?r+=oe(o,t?t.replace(/([^,])+/g,e=>a.replace(/([^,]*:\S+\([^)]*\))|([^,])+/g,t=>/&/.test(t)?t.replace(/&/g,e):e?e+` `+t:t)):a):o!=null&&(a=a[1]==`-`?a:a.replace(/[A-Z]/g,`-$&`).toLowerCase(),i+=oe.p?oe.p(a,o):a+`:`+o+`;`)}return n+(t&&i?t+`{`+i+`}`:i)+r},se={},ce=e=>{if(typeof e==`object`){let t=``;for(let n in e)t+=n+ce(e[n]);return t}return e},le=(e,t,n,r,i)=>{let a=ce(e),o=se[a]||(se[a]=(e=>{let t=0,n=11;for(;t<e.length;)n=101*n+e.charCodeAt(t++)>>>0;return`go`+n})(a));if(!se[o]){let t=a===e?(e=>{let t,n,r=[{}];for(;t=j.exec(e.replace(ie,``));)t[4]?r.shift():t[3]?(n=t[3].replace(ae,` `).trim(),r.unshift(r[0][n]=r[0][n]||{})):r[0][t[1]]=t[2].replace(ae,` `).trim();return r[0]})(e):e;se[o]=oe(i?{[`@keyframes `+o]:t}:t,n?``:`.`+o)}let s=n&&se.g;return n&&(se.g=se[o]),((e,t,n,r)=>{r?t.data=t.data.replace(r,e):t.data.indexOf(e)===-1&&(t.data=n?e+t.data:t.data+e)})(se[o],t,r,s),o},ue=(e,t,n)=>e.reduce((e,r,i)=>{let a=t[i];if(a&&a.call){let e=a(n),t=e&&e.props&&e.props.className||/^go/.test(e)&&e;a=t?`.`+t:e&&typeof e==`object`?e.props?``:oe(e,``):!1===e?``:e}return e+r+(a??``)},``);function de(e){let t=this||{},n=e.call?e(t.p):e;return le(n.unshift?n.raw?ue(n,[].slice.call(arguments,1),t.p):n.reduce((e,n)=>Object.assign(e,n&&n.call?n(t.p):n),{}):n,A(t.target),t.g,t.o,t.k)}var fe,pe,me;de.bind({g:1});var he=de.bind({k:1});function ge(e,t,n,r){oe.p=t,fe=e,pe=n,me=r}function _e(e,t){let n=this||{};return function(){let r=arguments;function i(a,o){let s=Object.assign({},a),c=s.className||i.className;n.p=Object.assign({theme:pe&&pe()},s),n.o=/go\d/.test(c),s.className=de.apply(n,r)+(c?` `+c:``),t&&(s.ref=o);let l=e;return e[0]&&(l=s.as||e,delete s.as),me&&l[0]&&me(s),fe(l,s)}return t?t(i):i}}var ve=e=>typeof e==`function`,ye=(e,t)=>ve(e)?e(t):e,be=(()=>{let e=0;return()=>(++e).toString()})(),xe=(()=>{let e;return()=>{if(e===void 0&&typeof window<`u`){let t=matchMedia(`(prefers-reduced-motion: reduce)`);e=!t||t.matches}return e}})(),Se=20,Ce=`default`,we=(e,t)=>{let{toastLimit:n}=e.settings;switch(t.type){case 0:return{...e,toasts:[t.toast,...e.toasts].slice(0,n)};case 1:return{...e,toasts:e.toasts.map(e=>e.id===t.toast.id?{...e,...t.toast}:e)};case 2:let{toast:r}=t;return we(e,{type:+!!e.toasts.find(e=>e.id===r.id),toast:r});case 3:let{toastId:i}=t;return{...e,toasts:e.toasts.map(e=>e.id===i||i===void 0?{...e,dismissed:!0,visible:!1}:e)};case 4:return t.toastId===void 0?{...e,toasts:[]}:{...e,toasts:e.toasts.filter(e=>e.id!==t.toastId)};case 5:return{...e,pausedAt:t.time};case 6:let a=t.time-(e.pausedAt||0);return{...e,pausedAt:void 0,toasts:e.toasts.map(e=>({...e,pauseDuration:e.pauseDuration+a}))}}},Te=[],Ee={toasts:[],pausedAt:void 0,settings:{toastLimit:Se}},De={},Oe=(e,t=Ce)=>{De[t]=we(De[t]||Ee,e),Te.forEach(([e,n])=>{e===t&&n(De[t])})},ke=e=>Object.keys(De).forEach(t=>Oe(e,t)),Ae=e=>Object.keys(De).find(t=>De[t].toasts.some(t=>t.id===e)),je=(e=Ce)=>t=>{Oe(t,e)},Me={blank:4e3,error:4e3,success:2e3,loading:1/0,custom:4e3},Ne=(e={},t=Ce)=>{let[n,r]=(0,y.useState)(De[t]||Ee),i=(0,y.useRef)(De[t]);(0,y.useEffect)(()=>(i.current!==De[t]&&r(De[t]),Te.push([t,r]),()=>{let e=Te.findIndex(([e])=>e===t);e>-1&&Te.splice(e,1)}),[t]);let a=n.toasts.map(t=>({...e,...e[t.type],...t,removeDelay:t.removeDelay||e[t.type]?.removeDelay||e?.removeDelay,duration:t.duration||e[t.type]?.duration||e?.duration||Me[t.type],style:{...e.style,...e[t.type]?.style,...t.style}}));return{...n,toasts:a}},Pe=(e,t=`blank`,n)=>({createdAt:Date.now(),visible:!0,dismissed:!1,type:t,ariaProps:{role:`status`,"aria-live":`polite`},message:e,pauseDuration:0,...n,id:n?.id||be()}),Fe=e=>(t,n)=>{let r=Pe(t,e,n);return je(r.toasterId||Ae(r.id))({type:2,toast:r}),r.id},Ie=(e,t)=>Fe(`blank`)(e,t);Ie.error=Fe(`error`),Ie.success=Fe(`success`),Ie.loading=Fe(`loading`),Ie.custom=Fe(`custom`),Ie.dismiss=(e,t)=>{let n={type:3,toastId:e};t?je(t)(n):ke(n)},Ie.dismissAll=e=>Ie.dismiss(void 0,e),Ie.remove=(e,t)=>{let n={type:4,toastId:e};t?je(t)(n):ke(n)},Ie.removeAll=e=>Ie.remove(void 0,e),Ie.promise=(e,t,n)=>{let r=Ie.loading(t.loading,{...n,...n?.loading});return typeof e==`function`&&(e=e()),e.then(e=>{let i=t.success?ye(t.success,e):void 0;return i?Ie.success(i,{id:r,...n,...n?.success}):Ie.dismiss(r),e}).catch(e=>{let i=t.error?ye(t.error,e):void 0;i?Ie.error(i,{id:r,...n,...n?.error}):Ie.dismiss(r)}),e};var Le=1e3,Re=(e,t=`default`)=>{let{toasts:n,pausedAt:r}=Ne(e,t),i=(0,y.useRef)(new Map).current,a=(0,y.useCallback)((e,t=Le)=>{if(i.has(e))return;let n=setTimeout(()=>{i.delete(e),o({type:4,toastId:e})},t);i.set(e,n)},[]);(0,y.useEffect)(()=>{if(r)return;let e=Date.now(),i=n.map(n=>{if(n.duration===1/0)return;let r=(n.duration||0)+n.pauseDuration-(e-n.createdAt);if(r<0){n.visible&&Ie.dismiss(n.id);return}return setTimeout(()=>Ie.dismiss(n.id,t),r)});return()=>{i.forEach(e=>e&&clearTimeout(e))}},[n,r,t]);let o=(0,y.useCallback)(je(t),[t]),s=(0,y.useCallback)(()=>{o({type:5,time:Date.now()})},[o]),c=(0,y.useCallback)((e,t)=>{o({type:1,toast:{id:e,height:t}})},[o]),l=(0,y.useCallback)(()=>{r&&o({type:6,time:Date.now()})},[r,o]),u=(0,y.useCallback)((e,t)=>{let{reverseOrder:r=!1,gutter:i=8,defaultPosition:a}=t||{},o=n.filter(t=>(t.position||a)===(e.position||a)&&t.height),s=o.findIndex(t=>t.id===e.id),c=o.filter((e,t)=>t<s&&e.visible).length;return o.filter(e=>e.visible).slice(...r?[c+1]:[0,c]).reduce((e,t)=>e+(t.height||0)+i,0)},[n]);return(0,y.useEffect)(()=>{n.forEach(e=>{if(e.dismissed)a(e.id,e.removeDelay);else{let t=i.get(e.id);t&&(clearTimeout(t),i.delete(e.id))}})},[n,a]),{toasts:n,handlers:{updateHeight:c,startPause:s,endPause:l,calculateOffset:u}}},ze=he`
from {
  transform: scale(0) rotate(45deg);
	opacity: 0;
}
to {
 transform: scale(1) rotate(45deg);
  opacity: 1;
}`,Be=he`
from {
  transform: scale(0);
  opacity: 0;
}
to {
  transform: scale(1);
  opacity: 1;
}`,Ve=he`
from {
  transform: scale(0) rotate(90deg);
	opacity: 0;
}
to {
  transform: scale(1) rotate(90deg);
	opacity: 1;
}`,He=_e(`div`)`
  width: 20px;
  opacity: 0;
  height: 20px;
  border-radius: 10px;
  background: ${e=>e.primary||`#ff4b4b`};
  position: relative;
  transform: rotate(45deg);

  animation: ${ze} 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275)
    forwards;
  animation-delay: 100ms;

  &:after,
  &:before {
    content: '';
    animation: ${Be} 0.15s ease-out forwards;
    animation-delay: 150ms;
    position: absolute;
    border-radius: 3px;
    opacity: 0;
    background: ${e=>e.secondary||`#fff`};
    bottom: 9px;
    left: 4px;
    height: 2px;
    width: 12px;
  }

  &:before {
    animation: ${Ve} 0.15s ease-out forwards;
    animation-delay: 180ms;
    transform: rotate(90deg);
  }
`,Ue=he`
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
`,We=_e(`div`)`
  width: 12px;
  height: 12px;
  box-sizing: border-box;
  border: 2px solid;
  border-radius: 100%;
  border-color: ${e=>e.secondary||`#e0e0e0`};
  border-right-color: ${e=>e.primary||`#616161`};
  animation: ${Ue} 1s linear infinite;
`,Ge=he`
from {
  transform: scale(0) rotate(45deg);
	opacity: 0;
}
to {
  transform: scale(1) rotate(45deg);
	opacity: 1;
}`,Ke=he`
0% {
	height: 0;
	width: 0;
	opacity: 0;
}
40% {
  height: 0;
	width: 6px;
	opacity: 1;
}
100% {
  opacity: 1;
  height: 10px;
}`,qe=_e(`div`)`
  width: 20px;
  opacity: 0;
  height: 20px;
  border-radius: 10px;
  background: ${e=>e.primary||`#61d345`};
  position: relative;
  transform: rotate(45deg);

  animation: ${Ge} 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275)
    forwards;
  animation-delay: 100ms;
  &:after {
    content: '';
    box-sizing: border-box;
    animation: ${Ke} 0.2s ease-out forwards;
    opacity: 0;
    animation-delay: 200ms;
    position: absolute;
    border-right: 2px solid;
    border-bottom: 2px solid;
    border-color: ${e=>e.secondary||`#fff`};
    bottom: 6px;
    left: 6px;
    height: 10px;
    width: 6px;
  }
`,Je=_e(`div`)`
  position: absolute;
`,Ye=_e(`div`)`
  position: relative;
  display: flex;
