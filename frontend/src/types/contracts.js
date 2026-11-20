/** @typedef {{id:number,name:string,source:string,rows:number,checksum:string}} Dataset */
/** @typedef {{asset:string,model:string,km:number,km_lower?:number,failed:number}} LifeRecord */
/** @typedef {{asset:string,kind:'exact'|'interval'|'censored',kind_label:string,lower:number|null,upper:number,sources:number,supplements:number}} Observation */
/** @typedef {{id:number,name:string,dataset_id:number,status:string,result:Object,approved:boolean,approved_at:number|null,root_id:number,revision:number,supplements:Array,superseded_by:number|null,fingerprint:string}} AnalysisJob */
/** @typedef {{id:number,name:string,job_id:number,destination:string,next_run:number,enabled:boolean}} ReportSchedule */
export {};
