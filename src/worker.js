import { McpServer } from "@modelcontextprotocol/server";
import { createMcpHandler } from "agents/mcp/server";
import { z } from "zod";

const SITE="https://openmodelweights.com";
const textResult=value=>({content:[{type:"text",text:JSON.stringify(value,null,2)}]});

async function assetJson(env,path){
  const response=await env.ASSETS.fetch(new Request(SITE+path));
  if(!response.ok) throw new Error("Open Model Weights asset unavailable: "+path);
  return response.json();
}
const norm=v=>(v??"").toString().toLowerCase();
const limitOf=v=>Math.max(1,Math.min(100,Number(v||20)));

function createServer(env){
  const server=new McpServer({name:"Open Model Weights",version:"1.0.0"});

  server.registerTool("search_models",{
    description:"Search field-verified open-weight model records. Returns evidence-backed fields; popularity is not a quality score.",
    inputSchema:{
      query:z.string().optional(),developer:z.string().optional(),license:z.string().optional(),
      commercial_use:z.string().optional(),format:z.string().optional(),
      min_context_tokens:z.number().nonnegative().optional(),max_int4_weight_gb:z.number().positive().optional(),
      limit:z.number().int().min(1).max(100).optional()
    }
  },async args=>{
    const data=await assetJson(env,"/api/v1/models.json"),q=norm(args.query),dev=norm(args.developer),lic=norm(args.license),fmt=norm(args.format);
    const models=(data.models||[]).filter(m=>{
      const hay=norm([m.name,m.developer,m.family,m.license?.name,(m.formats||[]).join(" ")].join(" "));
      const ctx=Number(m.model?.context?.value||0),mem=Number(m.hardware?.weight_only_gb?.int4??Infinity);
      return (!q||hay.includes(q))&&(!dev||norm(m.developer).includes(dev))&&(!lic||norm(m.license?.name).includes(lic))&&(!args.commercial_use||m.license?.commercial_use?.status===args.commercial_use)&&(!fmt||(m.formats||[]).some(x=>norm(x)===fmt))&&(!args.min_context_tokens||ctx>=args.min_context_tokens)&&(!args.max_int4_weight_gb||mem<=args.max_int4_weight_gb);
    }).slice(0,limitOf(args.limit));
    return textResult({count:models.length,models});
  });

  server.registerTool("get_model",{
    description:"Fetch the complete current field-verified record for one Open Model Weights model ID.",
    inputSchema:{model_id:z.string().regex(/^[a-z0-9-]+$/)}
  },async ({model_id})=>textResult(await assetJson(env,"/api/v1/models/"+encodeURIComponent(model_id)+".json")));

  server.registerTool("compare_models",{
    description:"Compare 2–4 verified model records neutrally across technical, legal, hardware, lineage and freshness fields.",
    inputSchema:{model_ids:z.array(z.string().regex(/^[a-z0-9-]+$/)).min(2).max(4)}
  },async ({model_ids})=>{
    const models=await Promise.all(model_ids.map(id=>assetJson(env,"/api/v1/models/"+encodeURIComponent(id)+".json")));
    const rows=models.map(m=>({id:m.id,name:m.name,developer:m.developer,parameters:m.model?.parameters,context:m.model?.context,license:m.license,formats:m.weights?.formats,precision:m.weights?.precision_availability,hardware:m.hardware,lineage:m.lineage,runtime_support:m.runtime_support,last_checked:m.verification?.checked_at}));
    return textResult({models:rows,note:"No winner or composite score is assigned."});
  });

  server.registerTool("find_compatible_models",{
    description:"Filter the structured compatibility graph by runtime/format/precision/context/commercial-use and weight-only memory constraints.",
    inputSchema:{
      runtime:z.string().optional(),format:z.string().optional(),precision:z.string().optional(),
      commercial_use:z.string().optional(),min_context_tokens:z.number().nonnegative().optional(),
      max_weight_memory_gb:z.number().positive().optional(),
      memory_mode:z.enum(["int4","fp8_int8","bf16_fp16"]).optional(),limit:z.number().int().min(1).max(100).optional()
    }
  },async args=>{
    const graph=await assetJson(env,"/api/v1/compatibility.json"),mode=args.memory_mode||"int4";
    const models=(graph.models||[]).filter(m=>(!args.runtime||m.runtimes?.includes(args.runtime))&&(!args.format||m.formats?.includes(args.format))&&(!args.precision||m.precisions?.includes(norm(args.precision)))&&(!args.commercial_use||m.commercial_use===args.commercial_use)&&(!args.min_context_tokens||Number(m.context_tokens||0)>=args.min_context_tokens)&&(!args.max_weight_memory_gb||Number(m.weight_only_gb?.[mode]??Infinity)<=args.max_weight_memory_gb)).slice(0,limitOf(args.limit));
    return textResult({count:models.length,memory_mode:mode,models,limitations:graph.semantics});
  });

  server.registerTool("get_model_history",{
    description:"Read the observed evidence ledger and revision diffs for a model. History only includes states Open Model Weights actually observed.",
    inputSchema:{model_id:z.string().regex(/^[a-z0-9-]+$/)}
  },async ({model_id})=>textResult(await assetJson(env,"/api/v1/evidence/"+encodeURIComponent(model_id)+".json")));

  server.registerTool("get_recent_changes",{
    description:"Read recent registry verification and publisher repository change events.",
    inputSchema:{limit:z.number().int().min(1).max(100).optional(),model_id:z.string().optional()}
  },async args=>{
    const data=await assetJson(env,"/api/v1/changes.json");
    let events=data.events||[];if(args.model_id)events=events.filter(x=>x.model_id===args.model_id);
    return textResult({generated_at:data.generated_at,events:events.slice(0,limitOf(args.limit))});
  });

  server.registerTool("get_registry_status",{
    description:"Return current registry count, schema version and verification freshness.",
    inputSchema:{}
  },async ()=>textResult(await assetJson(env,"/api/v1/meta.json")));

  server.registerTool("get_benchmark_protocol",{
    description:"Return the Open Model Weights reproducible deployment benchmark protocol. Results are only accepted with exact revision/runtime/hardware evidence.",
    inputSchema:{}
  },async ()=>textResult(await assetJson(env,"/benchmarks/protocol.json")));

  return server;
}

export default {
  fetch(request,env,ctx){
    const url=new URL(request.url);
    if(url.pathname==="/mcp"){
      const handler=createMcpHandler(()=>createServer(env),{
        route:"/mcp",
        allowedHostnames:["openmodelweights.com","www.openmodelweights.com"],
        allowedOriginHostnames:"*",
        legacy:"stateless",
        responseMode:"auto"
      });
      return handler(request,env,ctx);
    }
    return env.ASSETS.fetch(request);
  }
};