import random
import pytest
from backend.services import rules
from backend.services.storage import Storage

def test_spin_equal_probability():
    rng=random.Random(12)
    counts={n:0 for n in [3,4,5,6]}
    for _ in range(40000): counts[rules.spin(rng)]+=1
    assert all(abs(v-10000)<350 for v in counts.values())
def test_speaker_never_repeats():
    bots=[{'id':str(i)} for i in range(6)]
    assert all(rules.speaker(bots,'2')['id']!='2' for _ in range(300))
def test_direction():
    assert rules.direction([0,0,1])=='new_subject'
    with pytest.raises(ValueError): rules.direction([0,0,0])
    rng=random.Random(3); values=[rules.direction([40,25,35],rng) for _ in range(10000)]
    assert abs(values.count('respond')/len(values)-.25)<.02
def test_all_bingo_lines():
    assert len(rules.bingo_lines([True]*25))==12
    marks=[False]*25
    for i in [4,8,12,16,20]: marks[i]=True
    assert rules.bingo_lines(marks)==[[4,8,12,16,20]]
    marks[12]=False
    assert rules.bingo_lines(marks)==[]
def test_alias_and_boundaries():
    pool=rules.unique_pool(['Ellen Joe | shark maid','Nicole Demara','Soldier 11','Soldier 0 Anby'])
    assert rules.mentions('ELLEN! Nicole was there. Soldiers too.',pool)==['Ellen Joe','Nicole Demara']
    assert rules.mentions('The shark maid met Soldier.',pool)==['Ellen Joe']
    assert rules.mentions('Ellenish and Nicoleness',pool)==[]
def test_ambiguous_alias():
    pool=rules.unique_pool(['Jane Doe | Doe','Jane Smith | Doe'])
    assert rules.mentions('Jane and Doe',pool)==[]
    assert rules.mentions('Jane Doe',pool)==['Jane Doe']
def test_pool_uniqueness():
    assert rules.unique_pool(['Ellen',' ellen ','',{'name':'Nicole','aliases':['N',4]},None])==[{'name':'Ellen','aliases':[]},{'name':'Nicole','aliases':['N']}]
def test_chaos_probability_and_repeat():
    rng=random.Random(7)
    events=[rules.chaos_event('high','Alliance',rng) for _ in range(10000)]
    assert abs(sum(e is not None for e in events)/len(events)-.30)<.02
    assert 'Alliance' not in events
    assert rules.chaos_event('off',None) is None
@pytest.mark.parametrize('score,stance,expected',[(99,'agree',100),(-99,'disagree',-100),(0,'neutral',0),(0,'disagree',-8)])
def test_relationship(score,stance,expected): assert rules.relationship(score,stance,1)==expected
def test_storage(tmp_path):
    store=Storage(tmp_path);store.save('game',"name's save",{'board':['Ellen'],'settings':{'tts':False}})
    assert store.load('game',"name's save")['board']==['Ellen']
    assert store.list('game')==["name's save"]
    assert store.load('game','absent') is None

def test_ollama_validation():
    assert rules.clean_response('<think>secret</think>Hello!')=='Hello!'
    for bad in ['', '<think>hidden</think>', '<think>unfinished','x'*6001]:
        with pytest.raises(ValueError):rules.clean_response(bad)
