import {it,expect} from 'vitest';
import {formatTime,timerDuration} from './timer';
it('accepts arbitrary durations and normalizes mixed units',()=>{expect(timerDuration(2,75,90)).toBe(11790);expect(timerDuration(0,0,0)).toBe(1);expect(timerDuration(NaN,0,0)).toBe(1);});
it('formats hours and clamps expired timers',()=>{expect(formatTime(3661)).toBe('1:01:01');expect(formatTime(60)).toBe('1:00');expect(formatTime(-4)).toBe('0:00');expect(formatTime(.5)).toBe('0:01');});
