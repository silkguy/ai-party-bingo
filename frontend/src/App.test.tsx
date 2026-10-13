// @vitest-environment jsdom
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import App from './App';
import {initial,defaults} from './types';
const speech=vi.hoisted(()=>({cancelSpeech:vi.fn(),pauseSpeech:vi.fn(),resumeSpeech:vi.fn(),sound:vi.fn(),speak:vi.fn(async()=>{})}));
vi.mock('./speech',()=>speech);
const message={botId:'b1',name:'Nova',personality:'Nerd',color:'#fff',subject:'Ellen Joe',message:'Ellen is great. I like the design.',mentionedEntities:['Ellen Joe'],chaosEvent:null,relationships:{}};
let turnResolve:(r:Response)=>void,turnCalls:number;
beforeEach(()=>{turnCalls=0;localStorage.clear();localStorage.setItem('bingo-game',JSON.stringify({...initial,stage:4,board:Array.from({length:25},(_,i)=>'Entry '+i),pool:[{name:'Ellen Joe',aliases:[]}],bots:[{id:'b1',name:'Nova',color:'#fff',personality:'Nerd',description:'Nerd',voice:''}]}));localStorage.setItem('bingo-settings',JSON.stringify({...defaults,sounds:false}));vi.stubGlobal('speechSynthesis',{getVoices:()=>[],addEventListener:()=>{},removeEventListener:()=>{},cancel:()=>{}});vi.stubGlobal('fetch',vi.fn((url:string)=>{const response=(data:unknown)=>Promise.resolve(new Response(JSON.stringify(data)));if(url.endsWith('/turn')){turnCalls++;return new Promise<Response>(r=>{turnResolve=r;});}if(url.endsWith('/spin'))return response({count:3});if(url.endsWith('/catalog'))return response({personalities:{Nerd:'Nerd'},topics:[]});if(url.endsWith('/health'))return response({ok:true,message:'Ready'});if(url.endsWith('/voices'))return response({voices:[]});return response({});}));});
afterEach(()=>{cleanup();vi.useRealTimers();vi.unstubAllGlobals();vi.clearAllMocks();});
describe('playback',()=>{
 it('rapid start clicks create only one turn; stop ignores the pending result',async()=>{render(<App/>);fireEvent.click(screen.getByRole('button',{name:'Start'}));fireEvent.click(screen.getByRole('button',{name:'Pause'}));fireEvent.click(screen.getByRole('button',{name:'Resume'}));expect(turnCalls).toBe(1);fireEvent.click(screen.getByTitle('Stop'));await act(async()=>{turnResolve(new Response(JSON.stringify(message)));});expect(screen.queryByText('Ellen is great. I like the design.')).toBeNull();});
 it('pause keeps the completed turn and resume can request a new turn',async()=>{render(<App/>);fireEvent.click(screen.getByRole('button',{name:'Start'}));fireEvent.click(screen.getByRole('button',{name:'Pause'}));await act(async()=>{turnResolve(new Response(JSON.stringify(message)));});fireEvent.click(screen.getByTitle('Skip message'));await waitFor(()=>expect(screen.getByText(message.message)).toBeTruthy());await waitFor(()=>expect(screen.getByTitle('Next bot').hasAttribute('disabled')).toBe(false));expect(turnCalls).toBe(1);fireEvent.click(screen.getByRole('button',{name:'Resume'}));expect(turnCalls).toBe(2);fireEvent.click(screen.getByTitle('Stop'));await act(async()=>{turnResolve(new Response(JSON.stringify(message)));});});
});

describe('optional game timer',()=>{
 it('is disabled by default',()=>{render(<App/>);expect(screen.queryByLabelText('Game timer')).toBeNull();});
 it('pauses the countdown with playback and stops a pending turn at expiry',async()=>{
  vi.useFakeTimers({toFake:['setTimeout','setInterval','clearTimeout','clearInterval','performance']});
  localStorage.setItem('bingo-settings',JSON.stringify({...defaults,sounds:false,timerEnabled:true,timerSeconds:2}));
  render(<App/>);await act(async()=>{});
  fireEvent.click(screen.getByRole('button',{name:'Start'}));
  await act(async()=>{await vi.advanceTimersByTimeAsync(1000);});
  fireEvent.click(screen.getByRole('button',{name:'Pause'}));
  const remaining=screen.getByLabelText('Game timer').textContent;
  await act(async()=>{await vi.advanceTimersByTimeAsync(5000);});
  expect(screen.getByLabelText('Game timer').textContent).toBe(remaining);
  expect(speech.pauseSpeech).toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Resume'}));
  await act(async()=>{await vi.advanceTimersByTimeAsync(1400);});
  expect(screen.getByText('Time’s up')).toBeTruthy();
  expect(speech.cancelSpeech).toHaveBeenCalled();
  await act(async()=>{turnResolve(new Response(JSON.stringify(message)));});
  expect(screen.queryByText(message.message)).toBeNull();
 });
});

describe('spin wheel API',()=>{
 it('sends POST to the spin endpoint rather than falling through to static hosting',async()=>{
  localStorage.setItem('bingo-game',JSON.stringify(initial));
  render(<App/>);
  const button=screen.getByRole('button',{name:'SPIN THE WHEEL'});
  await waitFor(()=>expect(button.hasAttribute('disabled')).toBe(false));
  fireEvent.click(button);
  await waitFor(()=>expect(fetch).toHaveBeenCalledWith('/api/spin',expect.objectContaining({method:'POST'})));
 });
});

describe('local model and extra voice setup',()=>{
 it('offers downloaded models and three English Piper choices',async()=>{
  vi.mocked(fetch).mockImplementation((url)=>{
   const path=String(url);let data:unknown={};
   if(path.endsWith('/catalog'))data={personalities:{Nerd:'Nerd'},topics:[]};
   if(path.endsWith('/health'))data={ok:false,message:'Model missing',models:['qwen3:latest']};
   if(path.endsWith('/voices'))data={piperAvailable:true,voices:['en_US-lessac-medium','en_US-ryan-medium','en_GB-alan-medium'],labels:{'en_US-lessac-medium':'Lessac · English (US)','en_US-ryan-medium':'Ryan · English (US)','en_GB-alan-medium':'Alan · English (UK)'}};
   return Promise.resolve(new Response(JSON.stringify(data)));
  });
  render(<App/>);
  fireEvent.click(screen.getByTitle('Settings'));
  await waitFor(()=>expect(screen.getByLabelText('Downloaded Ollama models')).toBeTruthy());
  fireEvent.change(screen.getByLabelText('Downloaded Ollama models'),{target:{value:'qwen3:latest'}});
  expect((screen.getByLabelText('Model') as HTMLInputElement).value).toBe('qwen3:latest');
  fireEvent.click(screen.getByRole('button',{name:'Bots'}));
  await waitFor(()=>expect(screen.getByRole('option',{name:'Piper · Lessac · English (US)'})).toBeTruthy());
  expect(screen.getByRole('option',{name:'Piper · Ryan · English (US)'})).toBeTruthy();
  expect(screen.getByRole('option',{name:'Piper · Alan · English (UK)'})).toBeTruthy();
 });
});
