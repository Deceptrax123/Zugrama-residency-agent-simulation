import json
import unittest
from residency.communication_insights import communication_insights

PEOPLE=[{'id':'a','name':'Ada Lovelace','nickname':'Ada'},{'id':'b','name':'Bob Rao','nickname':'Bob'},{'id':'c','name':'Cleo','nickname':''}]
def visit(room,member,start=0,end=None):return {'conversation_id':room,'member_id':member,'joined_after_seq':start,'left_after_seq':end}
def message(seq,sender,body,room='ab',at=None):return {'seq':seq,'id':f'm{seq}','sender_id':sender,'body':body,'conversation_id':room,'created_at':seq if at is None else at}


class CommunicationInsightsTests(unittest.TestCase):
    def test_hidden_original_is_not_exposed_by_reported_two_hop_mention(self):
        messages=[message(1,'a','PRIVATE-ORIGINAL-ACACIA'),message(2,'b','Ada mentioned water quality yesterday.','bc')]
        visits=[visit('ab','a'),visit('ab','b'),visit('bc','b'),visit('bc','c')]
        result=communication_insights('c',messages,visits,PEOPLE,10);all_time=result['windows'][0]
        self.assertNotIn('PRIVATE-ORIGINAL-ACACIA',json.dumps(result))
        self.assertEqual(all_time['mentions'][0]['referenced_id'],'a');self.assertIn('not verified',all_time['mentions'][0]['verification'])
        self.assertEqual(all_time['graph']['edges'],[{'source':'b','target':'c','count':1}])
        self.assertEqual([p['id'] for p in all_time['connections']],['b'])

    def test_delivery_boundaries_exclude_prejoin_and_leave_gaps(self):
        messages=[message(1,'b','PRIVATE-BEFORE'),message(2,'b','Visible water quality idea'),message(3,'b','PRIVATE-GAP'),message(4,'a','Visible telescope calibration')]
        visits=[visit('ab','a',1,2),visit('ab','a',3),visit('ab','b')]
        result=communication_insights('a',messages,visits,PEOPLE,10)
        self.assertEqual(result['visible_messages'],2);self.assertNotIn('PRIVATE',json.dumps(result))
        window=result['windows'][0];self.assertEqual(window['stats']['sent'],1);self.assertEqual(window['stats']['received'],1)
        self.assertEqual(window['connections'][0]['sent'],1);self.assertEqual(window['connections'][0]['received'],1)

    def test_group_delivery_is_not_inferred_from_current_presence(self):
        messages=[message(1,'a','Astronomy telescope'),message(2,'a','Water quality'),message(3,'a','Crop monitoring')]
        visits=[visit('ab','a'),visit('ab','b',0,2),visit('ab','c',1)]
        result=communication_insights('a',messages,visits,PEOPLE,10)['windows'][0]
        self.assertEqual(result['stats']['sent'],3)
        self.assertEqual(result['graph']['edges'],[{'source':'a','target':'b','count':2},{'source':'a','target':'c','count':2}])
        self.assertEqual(result['timeline'][0]['recipients'],['c'])

    def test_windows_and_topic_sources_are_bounded_and_do_not_assign_topics(self):
        messages=[message(1,'a','Astronomy telescope calibration is useful.',at=1),message(2,'b','Water quality needs careful measurements.',at=990),message(3,'a','Water quality measurements support decisions.',at=995)]
        result=communication_insights('a',messages,[visit('ab','a'),visit('ab','b')],PEOPLE,1000)
        all_time,minute=result['windows'][:2]
        self.assertEqual(all_time['stats']['sent'],2);self.assertEqual(minute['stats']['sent'],1)
        self.assertTrue(any('water' in t['label'] for t in minute['topics']))
        self.assertTrue(any('astronomy' in t['label'] or 'telescope' in t['label'] for t in all_time['topics']))
        for topic in minute['topics']:
            self.assertTrue(topic['sources']);self.assertTrue(all(s['message_id'] in ('m2','m3') for s in topic['sources']))
        empty=communication_insights('a',[],[],PEOPLE,0)
        self.assertTrue(all(not w['topics'] and not w['graph']['edges'] for w in empty['windows']))


if __name__=='__main__':unittest.main()
