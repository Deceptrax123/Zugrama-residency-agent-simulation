'use client';
import katex from 'katex';
export type Shape={type:'line'|'circle'|'rect'|'text',x:number,y:number,x2?:number,y2?:number,r?:number,width?:number,height?:number,text?:string};
export type Board={id:string,room_id:string,owner_id:string,message_id:string,title:string,text:string,equations:string[],shapes:Shape[],created_at:number};
export type ToolRun={id:string,owner_id:string,name:string,status:string,call_number:number,arguments:Record<string,unknown>,result:unknown,created_at:number};
export type Capabilities={web_search:boolean,web_read:boolean,python_run:boolean,shared_boards:boolean};
export function Equation({value}:{value:string}){
 let html:string;
 try{html=katex.renderToString(value,{displayMode:true,throwOnError:true,trust:false,strict:'error',maxExpand:100,maxSize:20});}
 catch{return <pre className="live-document">{value}</pre>;}
 return <div className="board-equation" dangerouslySetInnerHTML={{__html:html}}/>;
}
export function Drawing({board}:{board:Board}){
 if(!board.shapes?.length)return null;
 return <svg className="board-drawing" viewBox="0 0 1000 1000" role="img" aria-label={board.title+' drawing'}><title>{board.title}</title>{board.shapes.map((s,i)=>{
 const props={stroke:'currentColor',strokeWidth:4,fill:'none'};
 if(s.type==='line')return <line key={i} {...props} x1={s.x} y1={s.y} x2={s.x2} y2={s.y2}/>;
 if(s.type==='circle')return <circle key={i} {...props} cx={s.x} cy={s.y} r={s.r}/>;
 if(s.type==='rect')return <rect key={i} {...props} x={s.x} y={s.y} width={s.width} height={s.height}/>;
 if(s.type==='text')return <text key={i} x={s.x} y={s.y} fill="currentColor" fontSize={28}>{s.text}</text>;
 return null;
 })}</svg>;
}
export default function AgentWorkspace({host,capabilities,runs=[],boards=[],name}:{host:boolean,capabilities?:Capabilities,runs?:ToolRun[],boards?:Board[],name:(id:string)=>string}){
 return <><section id="agent-tools" className="panel"><h2>Research & code</h2><p>{capabilities?.python_run?'Agents can choose to search public sources, read pages, run Python calculations, and add shared math or drawing boards during networking.':'Tool availability will appear when the residency host reconnects.'}</p><p className="helper">Python runs have a 2-second CPU limit and 256 MiB of memory. Standard library calculations are supported. Submitted Python code and its results appear on the shared live screen. Research and memory tool results stay private unless shared in a conversation. Public searches use the free Exa service; requests can fail when it is unavailable.</p>{runs.length?runs.map(run=><details className="live-note" key={run.id}><summary>{run.name} · {run.status} · {name(run.owner_id)}</summary><small>Decision {run.call_number} · {new Date(run.created_at*1000).toLocaleString()}</small><h3>Arguments</h3><pre className="live-document">{typeof run.arguments.code==='string'?run.arguments.code:JSON.stringify(run.arguments,null,2)}</pre><h3>Result</h3><pre className="live-document">{JSON.stringify(run.result,null,2)}</pre></details>):<p className="helper">No tool calls yet. Opening this page does not run a tool or start networking.</p>}</section><section id="shared-boards" className="live-section"><h2>Shared boards</h2><p className="helper">{host?'Boards across this event’s conversations.':'Only board entries your agent witnessed during its joined periods appear here.'} Equations, diagrams, code, and drafts can evolve through new entries.</p>{boards.length?boards.map(board=><article className="panel" key={board.id}><h3>{board.title}</h3><small>{name(board.owner_id)} · Room {board.room_id.slice(0,8)} · {new Date(board.created_at*1000).toLocaleString()}</small><p style={{whiteSpace:'pre-wrap'}}>{board.text}</p>{board.equations?.map((value,i)=><Equation key={i} value={value}/>)}<Drawing board={board}/><a href={'#conversation-message-'+board.message_id}>Conversation entry ↗</a></article>):<p className="helper">No witnessed board entries yet.</p>}</section></>;
}
