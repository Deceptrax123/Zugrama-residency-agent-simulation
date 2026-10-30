"""Read-only graph analysis of completed test artifacts; no models or services."""
from collections import Counter,deque
import json
from pathlib import Path
import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[1])]
from residency.communication_insights import aliases


def graph_analysis(directory):
    directory=Path(directory);stored=json.loads((directory/'graph.json').read_text())
    messages=json.loads((directory/'messages.json').read_text());visits=json.loads((directory/'visits.json').read_text())
    nodes={p['id']:p for p in stored['graph']['nodes'] if not p.get('npc')};edges=Counter()
    deliveries=[e for e in stored['deliveries'] if e['source'] in nodes and e['target'] in nodes]
    for e in deliveries:edges[(e['source'],e['target'])]+=1
    neighbours={n:set() for n in nodes};undirected=Counter()
    for (a,b),weight in edges.items():neighbours[a].add(b);undirected[tuple(sorted((a,b)))]+=weight
    distances={}
    for origin in nodes:
        distance={origin:0};queue=deque([origin])
        while queue:
            source=queue.popleft()
            for target in neighbours[source]:
                if target not in distance:distance[target]=distance[source]+1;queue.append(target)
        distances[origin]=distance
    total=sum(undirected.values());degrees=Counter()
    for (a,b),weight in undirected.items():degrees[a]+=weight;degrees[b]+=weight
    def modularity(groups):
        if not total:return 0
        return sum(sum(w for (a,b),w in undirected.items() if a in group and b in group)/total-(sum(degrees[n] for n in group)/(2*total))**2 for group in groups)
    # Weighted greedy agglomeration; deterministic ties. Communities are a
    # descriptive partition of this short-run contact graph, not stable identities.
    groups=[{n} for n in sorted(nodes)];score=modularity(groups)
    while True:
        best=None
        for i in range(len(groups)):
            for j in range(i+1,len(groups)):
                merged=[g for k,g in enumerate(groups) if k not in (i,j)]+[groups[i]|groups[j]]
                value=modularity(merged)
                if value>score+1e-12 and (best is None or value>best[0]+1e-12):best=(value,merged)
        if best is None:break
        score,groups=best
    incoming=Counter();outgoing=Counter();partners={n:set() for n in nodes}
    for (a,b),weight in edges.items():incoming[b]+=weight;outgoing[a]+=weight;partners[a].add(b);partners[b].add(a)
    periods=[];start=stored['graph']['started_at'];duration=stored['graph']['duration']
    for label,lo,hi in (('early',0,duration/3),('middle',duration/3,2*duration/3),('late',2*duration/3,duration+1)):
        chosen=[e for e in deliveries if lo<=e['at']-start<hi];pairs=Counter((nodes[e['source']]['name'],nodes[e['target']]['name']) for e in chosen)
        periods.append({'period':label,'deliveries':len(chosen),'top_pairs':[{'source':a,'target':b,'deliveries':c} for (a,b),c in pairs.most_common(5)]})
    # Explicit named references with an actual prior incoming hop. Candidates
    # require manual reading; merely naming a person does not prove a relay.
    import re
    alias=aliases(list(nodes.values()));recipients={m['seq']:{e['target'] for e in deliveries if e['seq']==m['seq']} for m in messages}
    seen=Counter();references=[]
    for m in messages:
        speaker=m['sender_id'];targets=recipients[m['seq']]
        for name,origin in alias.items():
            if origin==speaker or origin in targets or not targets or not seen[(origin,speaker)]:continue
            if re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',m['body'],re.IGNORECASE):
                references.append({'message':m['seq'],'speaker':nodes[speaker]['name'],'origin_named':nodes[origin]['name'],'delivered_to':[nodes[t]['name'] for t in targets],'quote':m['body']})
        for target in targets:seen[(speaker,target)]+=1
    result={'residents':len(nodes),'directed_edges':len(edges),'undirected_edges':len(undirected),'human_deliveries':sum(edges.values()),
        'strongly_connected':all(len(d)==len(nodes) for d in distances.values()),
        'reachable_directed_pairs':sum(len(d)-1 for d in distances.values()),
        'shortest_path_hop_counts':dict(sorted(Counter(v for d in distances.values() for v in d.values() if v).items())),
        'directed_diameter_reachable_pairs':max((v for d in distances.values() for v in d.values()),default=0),
        'reciprocal_pairs':sum((b,a) in edges for a,b in edges)//2,
        'communities':[[nodes[n]['name'] for n in sorted(group)] for group in sorted(groups,key=lambda g:-len(g))],
        'modularity':score,'community_method':'Weighted greedy modularity on undirected human delivery graph; NPC excluded.',
        'attention':[{'name':nodes[n]['name'],'received':incoming[n],'sent':outgoing[n],'partners':len(partners[n]),'received_fraction':incoming[n]/max(1,sum(incoming.values()))} for n in sorted(nodes,key=lambda n:-incoming[n])],
        'phases':periods,'explicit_named_relay_candidates':references,
        'hop_definition':'Static directed shortest contact paths, not demonstrated information transfer. Named relay candidates need semantic verification.'}
    return result


if __name__=='__main__':
    result=graph_analysis(sys.argv[1]);print(json.dumps(result,ensure_ascii=False,indent=2))
