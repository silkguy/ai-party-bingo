import hashlib
import io
import json
from pathlib import Path
import sys
import pytest
from backend.services import tts
from scripts import install_english_voices as installer

@pytest.mark.parametrize('installed,external,expected',[
    (True,None,[sys.executable,'-m','piper']),
    (False,'/external/piper',['/external/piper']),
    (False,None,None),
])
def test_piper_discovery_without_venv_activation(monkeypatch,installed,external,expected):
    monkeypatch.setattr(tts.importlib.util,'find_spec',lambda name:object() if installed else None)
    monkeypatch.setattr(tts.shutil,'which',lambda name:external)
    assert tts.piper_command()==expected

def test_pack_has_three_distinct_english_voices():
    assert len(installer.VOICE_PACK)==3
    assert set(v['id'] for v in installer.VOICE_PACK)==set(tts.VOICE_LABELS)
    for voice in installer.VOICE_PACK:
        assert voice['id'].startswith('en_')
        assert len(voice['files'])==3
        assert any(f['local'].endswith('.MODEL_CARD') for f in voice['files'])

def test_atomic_download_and_reuse(tmp_path):
    content=b'model data for test'
    metadata={'remote':'test.onnx','local':'test.onnx','size_bytes':len(content),'md5_digest':hashlib.md5(content).hexdigest()}
    calls=[]
    def opener(request,timeout):
        calls.append(request.full_url)
        return io.BytesIO(content)
    target=installer.download(metadata,tmp_path,opener)
    assert target.read_bytes()==content
    assert not list(tmp_path.glob('*.part'))
    installer.download(metadata,tmp_path,opener)
    assert len(calls)==1

def test_failed_download_keeps_existing_voice_and_cleans_partial(tmp_path):
    target=tmp_path/'test.onnx';target.write_bytes(b'existing voice')
    metadata={'remote':'test.onnx','local':target.name,'size_bytes':100,'md5_digest':'0'*32}
    with pytest.raises(ValueError,match='incomplete'):
        installer.download(metadata,tmp_path,lambda *args,**kwargs:io.BytesIO(b'bad'))
    assert target.read_bytes()==b'existing voice'
    assert not list(tmp_path.glob('*.part'))
