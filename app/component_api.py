"""Local component lab API, shared by the main app and the standalone lab."""
from aiohttp import web
from app.components import Components, ROOT


def install(app, registry=None):
    registry = registry or Components()

    async def page(request):return web.FileResponse(ROOT/'app/ui/components.html')

    async def library(request):
        assemblies=[registry.assemble(c['content']['id']+'@'+str(c['revision'])) for c in registry.list('configuration')]
        # Prefer documented propulsion evidence, then count source-backed parameters.
        assemblies.sort(key=lambda a:(a['propulsion_evidence']=='estimated',-sum(a['evidence_counts'][k] for k in ('specified','derived','measured'))))
        return web.json_response(dict(components=registry.list('component'),configurations=registry.list('configuration'),
            assemblies=assemblies,history=registry.history()),headers={'Cache-Control':'no-store'})

    async def validation(request):
        return web.FileResponse(ROOT/'docs/component-controller-comparison.json',headers={'Cache-Control':'no-store'})

    async def operation(request):
        body=await request.json()
        if not isinstance(body,dict):raise ValueError('Expected operation object')
        op=request.match_info['op']
        if op=='save':return web.json_response(registry.save(body.get('kind'),body.get('content'),body.get('expected_revision')))
        if op=='freeze':return web.json_response(registry.freeze(body.get('reference'),body.get('scenario','nominal'),body.get('seed',137)))
        registry.record(body.get('id'),body.get('result'))
        return web.json_response({'recorded':True})

    app.router.add_get('/components',page)
    app.router.add_get('/api/components',library)
    app.router.add_get('/api/components/validation',validation)
    app.router.add_post(r'/api/components/{op:save|freeze|record}',operation)
    return registry
