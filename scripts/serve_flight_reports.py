"""Loopback report viewer with byte-range video seeking (aiohttp FileResponse)."""
import argparse
from pathlib import Path
from aiohttp import web


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--directory',type=Path,default=Path('.local/validation'))
    parser.add_argument('--port',type=int,default=8142)
    args=parser.parse_args()
    app=web.Application()
    app.router.add_static('/',args.directory.resolve(),show_index=False,follow_symlinks=False)
    web.run_app(app,host='127.0.0.1',port=args.port,access_log=None)


if __name__=='__main__':main()
