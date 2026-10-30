// A complete owner index lets bounded upload batches retain the other residents.
export function snapshotOwners(snapshots:unknown,owners?:unknown):string[]{
 if(!Array.isArray(snapshots)||snapshots.length>51)throw Error('Publish at most fifty residents and one host.');
 const ids=owners===undefined?snapshots.map(s=>s?.owner_id):owners;
 if(!Array.isArray(ids)||ids.length>51||ids.filter(id=>id!=='host').length>50||new Set(ids).size!==ids.length||ids.some(id=>typeof id!=='string'||(id!=='host'&&!/^anonymous:[0-9a-f]{64}$/.test(id))))throw Error('Provide up to fifty unique resident owners and one host.');
 if(snapshots.some(s=>!s||!ids.includes(s.owner_id)))throw Error('Every snapshot must belong to the complete owner index.');
 return ids;
}
