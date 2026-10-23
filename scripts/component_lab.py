"""Start the component lab without loading models, PX4 or the fleet."""
import argparse
from aiohttp import web
from app.server import local_only, ROOT
from app.components import Components, DEFAULT_DB
from app.component_api import install


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',type=int,default=8152)
    p.add_argument('--db',default=str(DEFAULT_DB))
    args=p.parse_args()
    app=web.Application(middlewares=[local_only],client_max_size=1024*1024)
    install(app,Components(args.db))
    app.router.add_static('/assets/',ROOT/'app/ui',show_index=False)
    web.run_app(app,host='127.0.0.1',port=args.port)


if __name__=='__main__':main()
