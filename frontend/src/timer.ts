export function timerDuration(hours:number,minutes:number,seconds:number):number{
 const value=Math.floor(hours*3600+minutes*60+seconds);
 return Number.isFinite(value)&&value>0?value:1;
}
export function formatTime(seconds:number):string{
 const total=Math.max(0,Math.ceil(seconds));
 const h=Math.floor(total/3600),m=Math.floor(total%3600/60),s=total%60;
 return h>0?`${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`:`${m}:${String(s).padStart(2,'0')}`;
}
