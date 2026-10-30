import copy
import json
import unittest

from residency.site_bridge import SiteBridge
from residency.store import AppError
from tests.test_cohort import fixture,export,import_payload,apply
from tests.test_integration import Client
from tests import test_site_bridge


def drafts(count=3):
    rows=export(count)
    for index,row in enumerate(rows):
        data=json.loads(row['data']);data['identity']['moral_compass']='';data['identity']['political_standing']=''
        if index==1:data['memory']['network_context']=True
        else:data['memory']['capture_conversations']=False;data['memory']['recall_enabled']=False
        row.update(status='draft',markdown='',data=json.dumps(data),updated_at='2026-10-28T11:00:00Z')
        if index<2:row['host_review']={'approved':True,'note':'Skills, offers, needs and authored introduction are present. Optional moral answers remain blank.'}
    return rows


class HostDraftEnrollmentTests(unittest.TestCase):
    def test_explicit_host_approval_preserves_answers_choices_source_ids_and_no_start(self):
        with fixture() as (server,client,backend,memory):
            source=drafts();original=copy.deepcopy(source);payload=import_payload(source,use=True)
            preview=server.sandbox.preview_import(server.sandbox.owner,payload)
            self.assertEqual(preview['skipped_drafts'],1);self.assertEqual(len(preview['rows']),2)
            self.assertFalse(preview['rows'][0]['memory_policy']['network_context']);self.assertTrue(preview['rows'][1]['memory_policy']['network_context'])
            self.assertEqual(preview['rows'][0]['identity']['moral_compass'],'');self.assertEqual(preview['rows'][0]['identity']['political_standing'],'')
            self.assertEqual(preview['rows'][0]['identity']['introduction'],json.loads(source[0]['data'])['identity']['introduction'])
            self.assertEqual(preview['rows'][0]['enrollment_review']['basis'],'host_reviewed_draft')
            apply(server,client,payload);self.assertEqual(source,original)
            with server.store.db() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM cohort_enrollment_reviews').fetchone()[0],2)
                self.assertEqual({r[0] for r in db.execute('SELECT source_id FROM cohort_imports')},{r['user_id'] for r in source[:2]})
            bridge=test_site_bridge.SiteBridgeTests().bridge(server)
            snapshots={r['owner_id']:r['data'] for r in bridge.snapshots()}
            for row in source[:2]:self.assertEqual(snapshots[row['user_id']]['enrollment']['basis'],'host_reviewed_draft')
            self.assertNotIn('source_data_hash',json.dumps(snapshots));self.assertNotIn('Optional moral answers remain blank',json.dumps(snapshots))
            again=server.sandbox.preview_import(server.sandbox.owner,payload);self.assertTrue(all(r['action']=='unchanged' for r in again['rows']))
            result=apply(server,client,payload);self.assertEqual(result['imported_slots'],[])
            self.assertEqual(server.event.state['calls'],0);self.assertEqual(server.event.state['status'],'idle');self.assertEqual(backend.records,[])

    def test_unapproved_sparse_drafts_stay_skipped_and_invalid_approval_has_no_effect(self):
        with fixture() as (server,client,backend,memory):
            row=drafts(1)[0];row.pop('host_review')
            with self.assertRaises(AppError):server.sandbox.preview_import(server.sandbox.owner,import_payload([row]))
            for approval in ({'approved':False,'note':'No'},{'approved':True,'note':''},True):
                invalid={**row,'host_review':approval}
                with self.assertRaises(AppError):server.sandbox.preview_import(server.sandbox.owner,import_payload([invalid]))
            missing_intro=drafts(1)[0];data=json.loads(missing_intro['data']);data['identity']['introduction']='';missing_intro['data']=json.dumps(data)
            with self.assertRaises(AppError):server.sandbox.preview_import(server.sandbox.owner,import_payload([missing_intro]))
            self.assertEqual(server.sandbox.status(server.sandbox.owner)['agents'],[]);self.assertEqual(backend.records,[])

    def test_host_authorization_and_confirmation_cover_draft_approval(self):
        with fixture() as (server,client,backend,memory):
            payload=import_payload(drafts(2));visitor=Client(server.settings.public_origin)
            self.assertEqual(visitor.request('/api/cohort/import/preview','POST',payload)[0],401)
            code,preview,_=client.request('/api/cohort/import/preview','POST',payload);self.assertEqual(code,200)
            post={'import':payload,'preview_hash':preview['preview_hash'],'confirmed':True}
            self.assertEqual(client.request('/api/cohort/import/confirm','POST',post,{'X-CSRF-Token':'bad'})[0],403)
            changed=json.loads(payload['text']);changed['rows'][0]['host_review']['note']='Different host approval'
            changed_payload={**payload,'text':json.dumps(changed)}
            self.assertEqual(client.request('/api/cohort/import/confirm','POST',{**post,'import':changed_payload})[0],409)
            self.assertEqual(server.sandbox.status(server.sandbox.owner)['agents'],[]);self.assertEqual(backend.records,[])


if __name__=='__main__':unittest.main()
