(function(){
var root=document.body.getAttribute("data-root")||"";
try{var t=localStorage.getItem("mhdocs-theme");if(t)document.documentElement.setAttribute("data-theme",t)}catch(e){}
var tb=document.getElementById("theme");if(tb)tb.addEventListener("click",function(){var d=document.documentElement,cur=d.getAttribute("data-theme");if(!cur)cur=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";var n=cur==="dark"?"light":"dark";d.setAttribute("data-theme",n);try{localStorage.setItem("mhdocs-theme",n)}catch(e){}});
var nb=document.getElementById("navbtn");if(nb)nb.addEventListener("click",function(){document.body.classList.toggle("nav")});
var cur=document.querySelector(".side a.cur");if(cur&&cur.scrollIntoView)cur.scrollIntoView({block:"center"});
var q=document.getElementById("q"),res=document.getElementById("res"),idx=null,sel=-1;
function load(cb){if(idx)return cb();fetch(root+"search-index.json").then(function(r){return r.json()}).then(function(j){idx=j;cb()}).catch(function(){idx=[];cb()})}
function esc(s){return s.replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
function run(){var v=q.value.trim().toLowerCase();if(v.length<2){res.style.display="none";return}
load(function(){var w=v.split(/\s+/),out=[];idx.forEach(function(d){var h=(d.t+" "+d.x).toLowerCase(),sc=0;for(var i=0;i<w.length;i++){var p=h.indexOf(w[i]);if(p<0){sc=-1;break}sc+=d.t.toLowerCase().indexOf(w[i])>=0?5:1}if(sc>0){var p0=h.indexOf(w[0]),s=d.x.substr(Math.max(0,p0-d.t.length-1-40),120);out.push({d:d,sc:sc,s:s})}});
out.sort(function(a,b){return b.sc-a.sc});out=out.slice(0,12);
res.innerHTML=out.length?out.map(function(o){return '<a href="'+root+o.d.u+'"><b>'+esc(o.d.t)+'</b><small>'+esc(o.s)+'…</small></a>'}).join(""):'<a><small>No page found.</small></a>';res.style.display="block";sel=-1})}
if(q){q.addEventListener("input",run);q.addEventListener("keydown",function(e){var a=res.querySelectorAll("a[href]");if(e.key==="ArrowDown"&&a.length){sel=Math.min(a.length-1,sel+1)}else if(e.key==="ArrowUp"&&a.length){sel=Math.max(0,sel-1)}else if(e.key==="Enter"&&a.length){location.href=a[Math.max(0,sel)].getAttribute("href");return}else if(e.key==="Escape"){res.style.display="none";return}else return;e.preventDefault();a.forEach(function(x,i){x.classList.toggle("on",i===sel)})});
document.addEventListener("click",function(e){if(!e.target.closest(".search"))res.style.display="none"});
document.addEventListener("keydown",function(e){if(e.key==="/"&&document.activeElement.tagName!=="INPUT"){e.preventDefault();q.focus()}})}
})();