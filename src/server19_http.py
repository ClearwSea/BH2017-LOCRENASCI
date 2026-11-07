"""Local 1.9 dispatch/SDK HTTP endpoints; no outbound network requests."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
import json
import time


def dispatch(host="127.0.0.1", http_port=21018, game_port=21019, *, local_recharge=False):
    base = f"http://{host}:{http_port}"
    return {
        "retcode": 0,
        "gateway": {"ip": host, "port": game_port},
        "gameserver": {"ip": host, "port": game_port},
        "account_url": base + "/account",
        "account_url_backup": base + "/account",
        "asset_boundle_url": base + "/assets/",
        "is_data_ready": True,
        "server_cur_time": int(time.time()),
        "server_cur_timezone": 8,
        "ext": {
            "data_use_asset_boundle": False,
            "res_use_asset_boundle": False,
            "forbid_new_user": False,
            "forbid_recharge": not local_recharge,
            "recharge_max_limit": 0,
            "show_version_text": True,
            "oaserver_url": base + "/account",
            "ex_res_server_url": base + "/assets/",
            "ex_res_filename": "",
            "ex_res_video_path": "",
            "ex_res_buff_size": 0,
            "ex_res_version_code": 0,
        },
    }


def make_handler(event, host="127.0.0.1", port=21018, game_port=21019, *, local_recharge=False,
                 account_name="server19-local"):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def do_GET(self):
            self.respond()

        def do_POST(self):
            # Consume but do not log authentication values or personal fields.
            size = int(self.headers.get("Content-Length", "0"))
            if size > 1024 * 1024:
                self.send_error(413)
                return
            self.rfile.read(size)
            self.respond()

        def respond(self):
            path = urlsplit(self.path).path
            query_keys = sorted(parse_qs(urlsplit(self.path).query))
            event("http_request", method=self.command, path=path, query_keys=query_keys)
            base = f"http://{host}:{port}"
            if path == "/query_dispatch":
                data = {"retcode": 0, "region_list": [{"retcode": 0,
                        "dispatch_url": base + "/query_gateway", "name": "server19-local",
                        "title": "Local 1.9", "ext": {}}]}
            elif path == "/query_gateway":
                data = dispatch(host, port, game_port, local_recharge=local_recharge)
            elif path == "/health":
                data = {"status": "ok", "target": "1.9.0", "game_port": game_port}
            elif path in ("/account/sdk/login", "/account/sdk/token_login",
                          "/account/sdk/get_user_info_by_token"):
                # OriginalAccountManager's native response fields, using only a
                # local development identity. Fictional bound account info for offline play.
                data = {"retcode": 0, "message": "OK", "data": {
                    "uid": "1024", "token": "server19-local-only",
                    "name": account_name, "email": "github.com/ClearwSea", "mobile": "123*******0",
                    "is_email_verify": 1, "is_mobile_verify": 1, "is_realname_verify": 1,
                    "realname": "琪亚娜", "identity_card": "110101199812071234"}}
            else:
                # Unknown SDK routes must be researched rather than falsely acknowledged.
                event("http_unknown", path=path)
                self.send_error(404)
                return
            payload = json.dumps(data, separators=(",", ":")).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def serve(event, bind="127.0.0.1", advertised_host="127.0.0.1", port=21018, game_port=21019, *, local_recharge=False):
    server = ThreadingHTTPServer((bind, port), make_handler(event, advertised_host, port, game_port,
                                                         local_recharge=local_recharge))
    event("http_listen", bind=bind, port=port)
    server.serve_forever()
