"""In cây observation của 1 trace từ Langfuse v2 observations API (không in key)."""
import os, sys, httpx, json
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv; load_dotenv('.env')
auth=(os.environ['LANGFUSE_PUBLIC_KEY'], os.environ['LANGFUSE_SECRET_KEY'])
now=datetime.now(timezone.utc)
params={'fromStartTime':(now-timedelta(hours=6)).isoformat(),'toStartTime':now.isoformat(),'limit':100,
        'fields':'core,basic,time,io,metadata,model,usage,prompt,metrics'}
if len(sys.argv)>1: params['traceId']=sys.argv[1]
r=httpx.get(os.environ['LANGFUSE_BASE_URL']+'/api/public/v2/observations', auth=auth, timeout=30, params=params)
if r.status_code!=200: print(r.status_code, r.text[:500]); sys.exit(1)
rows=sorted(r.json()['data'], key=lambda o:o['startTime'])
names={o['id']:o['name'] for o in rows}
for o in rows:
    md=o.get('metadata') or {}
    print(f"{o['type']:10} {o['name']:20} parent={names.get(o.get('parentObservationId'),'(root)'):20} "
          f"model={o.get('providedModelName') or o.get('model')} prompt={o.get('promptName')} v{o.get('promptVersion')} "
          f"usage={o.get('usageDetails')} cost={o.get('costDetails')} level={o.get('level')} "
          f"cid={md.get('correlation_id') if isinstance(md,dict) else md}")
