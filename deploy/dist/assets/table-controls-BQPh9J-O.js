import{c as l,j as e,l as h,Q as u}from"./index-zM5ecsrN.js";import{i as p}from"./table-Cw_NLz1C.js";/**
 * @license lucide-react v0.364.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const m=l("ArrowDown",[["path",{d:"M12 5v14",key:"s699le"}],["path",{d:"m19 12-7 7-7-7",key:"1idqje"}]]);/**
 * @license lucide-react v0.364.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const b=l("ArrowUp",[["path",{d:"m5 12 7-7 7 7",key:"hav0vg"}],["path",{d:"M12 19V5",key:"x0mq9r"}]]);/**
 * @license lucide-react v0.364.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const f=l("ChevronLeft",[["path",{d:"m15 18-6-6 6-6",key:"1wnfg3"}]]);/**
 * @license lucide-react v0.364.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const g=l("ChevronsUpDown",[["path",{d:"m7 15 5 5 5-5",key:"1hf1tw"}],["path",{d:"m7 9 5-5 5 5",key:"sgt6xg"}]]);function N({sortKey:r,activeKey:n,dir:d,onSort:i,children:o,className:a,align:s="left"}){const c=n===r,t=c?d==="asc"?b:m:g;return e.jsx(p,{className:a,"aria-sort":c?d==="asc"?"ascending":"descending":"none",children:e.jsxs("button",{type:"button",onClick:()=>i(r),className:h("inline-flex items-center gap-1 rounded transition-colors hover:text-foreground",c?"font-semibold text-foreground":"text-inherit",s==="right"&&"flex-row-reverse",s==="center"&&"justify-center"),children:[o,e.jsx(t,{className:h("h-3 w-3 shrink-0",c?"opacity-90":"opacity-40")})]})})}const v=[10,20,50,100];function j(r,n){if(n<=7)return Array.from({length:n},(a,s)=>s+1);const d=new Set([1,n,r]);r-1>1&&d.add(r-1),r+1<n&&d.add(r+1);const i=[...d].sort((a,s)=>a-s),o=[];return i.forEach((a,s)=>{s>0&&a-i[s-1]>1&&o.push("gap"),o.push(a)}),o}function k({page:r,pageCount:n,pageSize:d,total:i,onPageChange:o,onPageSizeChange:a}){if(i===0)return null;const s=j(r,n),c="flex h-7 w-7 items-center justify-center rounded border border-input text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent";return e.jsxs("div",{className:"flex flex-col-reverse items-center justify-between gap-3 border-t border-border pt-3 text-xs sm:flex-row",children:[e.jsxs("div",{className:"flex items-center gap-3 text-muted-foreground",children:[e.jsxs("span",{children:["共 ",i," 条"]}),e.jsx("span",{className:"hidden sm:inline",children:"·"}),e.jsxs("label",{className:"hidden items-center gap-1.5 sm:flex",children:["每页",e.jsx("select",{value:d,onChange:t=>a(Number(t.target.value)),"aria-label":"每页条数",className:"h-7 rounded border border-input bg-background px-1.5 text-xs",children:v.map(t=>e.jsx("option",{value:t,children:t},t))}),"条"]})]}),e.jsxs("div",{className:"flex items-center gap-1",children:[e.jsx("button",{type:"button",className:c,onClick:()=>o(r-1),disabled:r<=1,"aria-label":"上一页",children:e.jsx(f,{className:"h-3.5 w-3.5"})}),s.map((t,x)=>t==="gap"?e.jsx("span",{className:"px-1 text-muted-foreground",children:"…"},`gap-${x}`):e.jsx("button",{type:"button",onClick:()=>o(t),"aria-current":t===r?"page":void 0,className:h("h-7 min-w-7 rounded border px-1.5 transition-colors",t===r?"border-primary bg-primary text-primary-foreground":"border-input text-muted-foreground hover:bg-accent hover:text-accent-foreground"),children:t},t)),e.jsx("button",{type:"button",className:c,onClick:()=>o(r+1),disabled:r>=n,"aria-label":"下一页",children:e.jsx(u,{className:"h-3.5 w-3.5"})})]})]})}export{b as A,N as S,k as T};
