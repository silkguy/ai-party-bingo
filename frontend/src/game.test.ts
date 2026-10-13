import {describe,it,expect} from 'vitest';
import {lines,shuffled} from './game';
describe('bingo',()=>{it('detects twelve lines',()=>expect(lines(Array(25).fill(true))).toHaveLength(12));it('does not count incomplete lines',()=>expect(lines(Array(25).fill(false))).toHaveLength(0));it('shuffles without adding or losing entries',()=>{const input=Array.from({length:25},(_,i)=>i);expect(shuffled(input).sort((a,b)=>a-b)).toEqual(input);});});
