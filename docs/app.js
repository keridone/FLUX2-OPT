const state={data:null,points:[],activeIndex:null,metric:"throughput"};
const fmt=new Intl.NumberFormat("zh-CN",{maximumFractionDigits:2});
async function loadData(){const r=await fetch("./data/optimization-history.json");if(!r.ok)throw new Error("无法加载优化历史数据");state.data=await r.json();renderPage()}
function renderPage(){
 const d=state.data,n=d.nodes;
 document.querySelector("#node-list").innerHTML=n.map(renderNodeCard).join("");
 document.querySelector("#bottleneck-list").innerHTML=d.bottlenecks.map(x=>'<div class="bottleneck-row"><div class="bottleneck-name"><strong>'+x.name+"</strong><span>"+x.type+'</span></div><div class="bar-track"><div class="bar-fill '+x.tone+'" style="width:'+Math.min(x.share*2.2,100)+'%"></div></div><div class="bottleneck-value">'+x.share.toFixed(1)+"%</div></div>").join("");
 document.querySelector("#roadmap-grid").innerHTML=d.roadmap.map(x=>'<article class="roadmap-card"><span class="roadmap-rank">'+x.rank+"</span><h3>"+x.title+"</h3><p>"+x.text+"</p></article>").join("");
 setupChart();renderChartKpis();
}
function tasksPerSecond(node){return node.metrics.tasksPerSecond||1/node.metrics.medianSeconds}
function renderChartKpis(){
 const n=state.data.nodes,latest=n.at(-1),first=n[0],throughput=tasksPerSecond(latest),throughputGain=(throughput/tasksPerSecond(first)-1)*100;
 const k=state.metric==="throughput"?[["Current throughput",throughput.toFixed(3)+" task/s","accent"],["Throughput gain","+"+throughputGain.toFixed(2)+"%","accent"],["Current median",latest.metrics.medianSeconds.toFixed(3)+" s",""],["Nodes measured",String(n.length),""]]:[["Current median",latest.metrics.medianSeconds.toFixed(3)+" s",""],["Total speedup","+"+latest.gainPercent.toFixed(2)+"%","accent"],["P95 latency",latest.metrics.p95Seconds.toFixed(3)+" s",""],["Time saved / run",(first.metrics.medianSeconds-latest.metrics.medianSeconds).toFixed(3)+" s","accent"]];
 document.querySelector("#chart-kpis").innerHTML=k.map(x=>'<div class="kpi"><span>'+x[0]+'</span><strong class="'+x[2]+'">'+x[1]+"</strong></div>").join("");
}
function renderNodeCard(n){
 const m=n.metrics,metrics=[["Median",m.medianSeconds.toFixed(3)+"s"],["P95",m.p95Seconds.toFixed(3)+"s"],["Peak VRAM",fmt.format(m.peakVramMiB)+" MiB"],["Peak RAM",fmt.format(m.peakRamMiB)+" MiB"],["Quality",m.qualityPassPercent+"%"]];
 return '<article class="node-card" id="'+n.id+'"><div class="node-rail"><span class="node-number">'+String(n.sequence).padStart(2,"0")+'</span></div><div class="node-body"><div class="node-title-row"><div><span class="node-label">'+n.label+" · "+n.method+"</span><h3>"+n.headline+'</h3></div><span class="status-pill '+n.status+'">'+n.status+'</span></div><p class="node-summary">'+n.summary+'</p><div class="node-metrics">'+metrics.map(x=>'<div class="metric-cell"><span>'+x[0]+"</span><strong>"+x[1]+"</strong></div>").join("")+'</div><div class="node-bottom"><ul class="detail-list">'+n.details.map(x=>"<li>"+x+"</li>").join("")+'</ul><div class="node-links">'+n.links.map(x=>'<a href="'+x.href+'">'+x.label+" ↗</a>").join("")+"</div></div></div></article>";
}
function setupChart(){
 const c=document.querySelector("#history-chart"),controls=document.querySelector("#chart-focus-controls");
 new ResizeObserver(drawChart).observe(c.parentElement);c.addEventListener("mousemove",onChartMove);c.addEventListener("mouseleave",()=>{state.activeIndex=null;hideTooltip();drawChart()});c.addEventListener("click",activateNearest);
 controls.innerHTML=state.data.nodes.map((n,i)=>'<button class="chart-point-button" data-index="'+i+'" aria-label="'+n.label+"，中位延迟 "+n.metrics.medianSeconds+' 秒"></button>').join("");
 controls.querySelectorAll("button").forEach(b=>{b.addEventListener("focus",()=>showPoint(Number(b.dataset.index)));b.addEventListener("blur",hideTooltip);b.addEventListener("click",()=>showPoint(Number(b.dataset.index)))});
 document.querySelectorAll(".metric-toggle button").forEach(b=>b.addEventListener("click",()=>setChartMetric(b.dataset.metric)));
}
function setChartMetric(metric){
 state.metric=metric;state.activeIndex=null;hideTooltip();
 document.querySelectorAll(".metric-toggle button").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.metric===metric)));
 const throughput=metric==="throughput";
 document.querySelector("#chart-title").textContent=throughput?"每秒任务数演进":"端到端延迟演进";
 document.querySelector("#chart-legend").innerHTML="<span></span> "+(throughput?"Derived throughput · 越高越好":"Median latency · 越低越好");
 document.querySelector("#history-chart").setAttribute("aria-label",throughput?"FLUX.2 每秒任务数优化折线图":"FLUX.2 端到端延迟优化折线图");
 renderChartKpis();drawChart();
}
function drawChart(){
 const c=document.querySelector("#history-chart"),r=c.getBoundingClientRect(),dpr=window.devicePixelRatio||1;c.width=Math.max(1,Math.floor(r.width*dpr));c.height=Math.max(1,Math.floor(r.height*dpr));
 const ctx=c.getContext("2d");ctx.scale(dpr,dpr);const w=r.width,h=r.height,p={l:68,r:35,t:30,b:58},throughput=state.metric==="throughput",v=state.data.nodes.map(n=>throughput?tasksPerSecond(n):n.metrics.medianSeconds),spread=Math.max(...v)-Math.min(...v),margin=Math.max(spread*.18,throughput?.015:.2),min=Math.max(0,Math.min(...v)-margin),max=Math.max(...v)+margin;
 ctx.font="10px 'DM Mono'";ctx.textBaseline="middle";
 for(let i=0;i<=4;i++){const y=p.t+(h-p.t-p.b)*i/4,val=max-(max-min)*i/4;ctx.strokeStyle="rgba(255,255,255,.08)";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(p.l,y);ctx.lineTo(w-p.r,y);ctx.stroke();ctx.fillStyle="#697183";ctx.textAlign="right";ctx.fillText(throughput?val.toFixed(2):val.toFixed(1)+"s",p.l-12,y)}
 state.points=state.data.nodes.map((n,i)=>{const value=throughput?tasksPerSecond(n):n.metrics.medianSeconds;return{x:state.data.nodes.length===1?w/2:p.l+(w-p.l-p.r)*i/(state.data.nodes.length-1),y:p.t+(max-value)/(max-min)*(h-p.t-p.b),node:n,index:i,value}});
 const g=ctx.createLinearGradient(0,p.t,0,h-p.b);g.addColorStop(0,"rgba(183,255,60,.22)");g.addColorStop(1,"rgba(183,255,60,0)");
 ctx.beginPath();state.points.forEach((x,i)=>i?ctx.lineTo(x.x,x.y):ctx.moveTo(x.x,x.y));ctx.lineTo(state.points.at(-1).x,h-p.b);ctx.lineTo(state.points[0].x,h-p.b);ctx.closePath();ctx.fillStyle=g;ctx.fill();
 ctx.beginPath();state.points.forEach((x,i)=>i?ctx.lineTo(x.x,x.y):ctx.moveTo(x.x,x.y));ctx.strokeStyle="#b7ff3c";ctx.lineWidth=2.5;ctx.stroke();
 state.points.forEach((x,i)=>{const a=state.activeIndex===i;ctx.beginPath();ctx.arc(x.x,x.y,a?8:6,0,Math.PI*2);ctx.fillStyle="#090b10";ctx.fill();ctx.strokeStyle="#b7ff3c";ctx.lineWidth=a?4:3;ctx.stroke();ctx.fillStyle="#f3f5f7";ctx.textAlign="center";ctx.font="500 10px 'DM Mono'";ctx.fillText(x.node.label.toUpperCase(),x.x,h-p.b+34);ctx.font="10px 'DM Mono'"});
 document.querySelectorAll(".chart-point-button").forEach((b,i)=>{b.style.left=state.points[i].x+"px";b.style.top=state.points[i].y+"px"});
}
function coords(e){const r=e.currentTarget.getBoundingClientRect();return{x:e.clientX-r.left,y:e.clientY-r.top}}
function nearest(x,y){return state.points.map((p,i)=>({i,d:Math.hypot(p.x-x,p.y-y)})).sort((a,b)=>a.d-b.d)[0]}
function onChartMove(e){const c=coords(e),n=nearest(c.x,c.y);if(n.d<44)showPoint(n.i);else{state.activeIndex=null;hideTooltip();drawChart()}}
function activateNearest(e){const c=coords(e),n=nearest(c.x,c.y);if(n.d<44)showPoint(n.i)}
function showPoint(i){
 state.activeIndex=i;drawChart();const p=state.points[i],n=p.node,m=n.metrics,t=document.querySelector("#chart-tooltip"),gain=n.gainPercent?"+"+n.gainPercent.toFixed(2)+"%":"BASELINE";
 const value=state.metric==="throughput"?tasksPerSecond(n).toFixed(3)+" task/s":m.medianSeconds.toFixed(3)+"s";
 t.innerHTML='<div class="tooltip-top"><span>'+n.label+'</span></div><div class="tooltip-value">'+value+'</div><div class="tooltip-method">'+n.method+" · "+gain+'</div><div class="tooltip-summary">Median '+m.medianSeconds.toFixed(3)+'s · P95 '+m.p95Seconds.toFixed(3)+"s<br>VRAM "+fmt.format(m.peakVramMiB)+" MiB · "+n.summary+"</div>";
 const wrap=document.querySelector(".canvas-wrap");t.style.left=Math.max(130,Math.min(p.x,wrap.clientWidth-130))+"px";t.style.top=Math.max(115,p.y)+"px";t.classList.add("visible");
}
function hideTooltip(){document.querySelector("#chart-tooltip").classList.remove("visible")}
loadData().catch(e=>{document.querySelector("#chart-kpis").innerHTML="<p>数据加载失败："+e.message+"</p>"});
