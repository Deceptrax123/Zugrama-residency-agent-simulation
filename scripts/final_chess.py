"""Reconstruct only recorded moves. Illegal or unrecorded continuations are never invented."""
from pathlib import Path
import json,re,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'.tools/report-libs'))
import chess
base=ROOT/'.data/live-residency/final-results/5ca0be9108194c68af3b0f0d8fda0e64';bundle=json.loads((base/'bundle.json').read_text());run=next(r for r in bundle['runs'] if r['id']==bundle['current_event_id']);replays=[]
for task in run['tasks']:
 if 'chess' not in task['title'].lower():continue
 revision=task['revisions'][-1];found=re.search(r'Score:\s*(.*?)(?:\n\n|$)',revision['body'],re.S)
 if not found:continue
 score=found.group(1);tokens=re.sub(r'\d+\.(?:\.\.)?',' ',score).split();board=chess.Board();positions=[{'fen':board.fen(),'move':'Start'}];error=None
 for token in tokens:
  try:move=board.parse_san(token.rstrip('.'));board.push(move);positions.append({'fen':board.fen(),'move':token,'uci':move.uci(),'message_id':revision['message_id']})
  except ValueError as exc:error={'token':token,'after_ply':len(positions)-1,'error':str(exc)};break
 replays.append({'id':task['id'],'title':task['title'],'room_id':task['room_id'],'message_id':revision['message_id'],'revision':revision['revision'],'score':score,'positions':positions,'error':error,'verification':'Post-event legality check with python-chess 1.11.2 against the latest cumulative score. This does not evaluate move quality or imply the original agents used a chess engine. The game is unfinished.'})
# This separate recorded game uses explicit, alternating move announcements.
room='07d90bca66f34f1085565991c2eca06b';board=chess.Board();positions=[{'fen':board.fen(),'move':'Start'}];tokens=[];mids=[];error=None
for m in run['messages']:
 if m['conversation_id']!=room:continue
 match=re.search(r'\b(\d+)\.(\.\.)?\s*(\S+)',m['body'][:35])
 if not match:continue
 number=int(match[1]);black=bool(match[2]);token=match[3].rstrip('.')
 try:
  if number!=board.fullmove_number or black!=(not board.turn):raise ValueError('Move order or side does not match the recorded position')
  move=board.parse_san(token);board.push(move)
 except ValueError as exc:error={'token':token,'after_ply':len(positions)-1,'error':str(exc)};break
 positions.append({'fen':board.fen(),'move':token,'uci':move.uci(),'message_id':m['id']});tokens.append(('' if black else str(number)+'. ')+token);mids.append(m['id'])
if mids:replays.append({'id':'marina-hiro-chess','title':'Marina–Hiro: chess with running commentary','room_id':room,'message_id':mids[-1],'revision':None,'score':' '.join(tokens),'positions':positions,'error':error,'verification':'Explicit move announcements checked in temporal order with python-chess 1.11.2. Each position links to its source. The game is unfinished.'})
(base/'chess.json').write_text(json.dumps(replays,indent=2));print(json.dumps([{'title':r['title'],'plies':len(r['positions'])-1,'error':r['error']} for r in replays]))
